package cloner

import (
	"context"
	"errors"
	"fmt"
	"log"
	"sync"
	"time"

	"github.com/FolcloreX/teleclone/internal/config"
	"github.com/gotd/td/telegram"
	"github.com/gotd/td/tg"
)

type Cloner struct {
	client *telegram.Client
	api    *tg.Client
	cfg    *config.Config
}

func New(client *telegram.Client, cfg *config.Config) *Cloner {
	return &Cloner{
		client: client,
		api:    tg.NewClient(client),
		cfg:    cfg,
	}
}

func (c *Cloner) resolveChannel(ctx context.Context, channelID int64, channelName string) (*tg.Channel, error) {
	input := &tg.InputChannel{ChannelID: channelID}

	resolved, err := c.api.ChannelsGetChannels(ctx, []tg.InputChannelClass{input})
	if err != nil {
		return nil, fmt.Errorf("não foi possível resolver o canal de %s (ID: %d). Verifique o ID e se a conta é membro: %w", channelName, channelID, err)
	}

	chats, ok := resolved.(*tg.MessagesChats)
	if !ok {
		return nil, fmt.Errorf("a API retornou um tipo inesperado ao resolver o canal de %s: %T", channelName, resolved)
	}
	if len(chats.Chats) == 0 {
		return nil, fmt.Errorf("a API não retornou informações para o canal de %s (ID: %d)", channelName, channelID)
	}

	channel, ok := chats.Chats[0].(*tg.Channel)
	if !ok {
		return nil, fmt.Errorf("o ID fornecido para o canal de %s não é um canal, mas um %T", channelName, chats.Chats[0])
	}

	return channel, nil
}

func (c *Cloner) Start(ctx context.Context) error {
	log.Println("Resolvendo e verificando os grupos de origem e destino, um por um...")

	originChannel, err := c.resolveChannel(ctx, c.cfg.OriginChatID, "origem")
	if err != nil {
		return err
	}
	log.Printf("Canal de origem '%s' resolvido com sucesso.", originChannel.Title)

	destinyChannel, err := c.resolveChannel(ctx, c.cfg.DestinyChatID, "destino")
	if err != nil {
		return err
	}
	log.Printf("Canal de destino '%s' resolvido com sucesso.", destinyChannel.Title)

	// TODO If the group is private we have to implement different logic
	if originChannel.Noforwards {
		log.Println("======================================================================")
		log.Printf("ERRO: O grupo de origem '%s' tem a proteção de encaminhamento ativada.", originChannel.Title)
		log.Println("======================================================================")
		return errors.New("grupo de origem é protegido contra encaminhamento")
	}
	log.Printf("Permissões verificadas. O grupo de origem permite o encaminhamento.")

	// Preparing the peers for the pipeline
	originInputPeer := &tg.InputPeerChannel{
		ChannelID:  originChannel.ID,
		AccessHash: originChannel.AccessHash,
	}

	destinyInputPeer := &tg.InputPeerChannel{
		ChannelID:  destinyChannel.ID,
		AccessHash: destinyChannel.AccessHash,
	}

	return c.runForwardingPipeline(ctx, originInputPeer, destinyInputPeer)
}

func (c *Cloner) runForwardingPipeline(ctx context.Context, originPeer, destinyPeer tg.InputPeerClass) error {
	var wg sync.WaitGroup
	wg.Add(2)
	messagesIDsChan := make(chan int, 100)

	log.Println("Iniciando pipeline de encaminhamento...")
	go c.fetchMessageIDs(ctx, &wg, originPeer, messagesIDsChan)
	go c.forwardMessages(ctx, &wg, originPeer, destinyPeer, messagesIDsChan)

	wg.Wait()
	log.Println("Processo de encaminhamento concluído.")
	return nil
}

func (c *Cloner) fetchMessageIDs(ctx context.Context, wg *sync.WaitGroup, originPeer tg.InputPeerClass, messagesIDsChan chan<- int) {
	defer wg.Done()
	defer close(messagesIDsChan)

	log.Printf("Iniciando busca de IDs de mensagens...")
	offsetID := 0
	const limit = 100

	for {
		if ctx.Err() != nil {
			log.Println("Contexto cancelado, parando a busca de mensagens.")
			return
		}
		history, err := c.api.MessagesGetHistory(ctx, &tg.MessagesGetHistoryRequest{Peer: originPeer, OffsetID: offsetID, Limit: limit})
		if err != nil {
			log.Printf("Erro ao buscar histórico: %v", err)
			return
		}
		messages, ok := history.(*tg.MessagesChannelMessages)
		if !ok {
			log.Printf("Não foi possível converter o histórico. Fim da busca.")
			return
		}
		if len(messages.Messages) == 0 {
			log.Println("Nenhuma mensagem nova encontrada. Busca finalizada.")
			return
		}
		for _, msg := range messages.Messages {
			if m, ok := msg.(*tg.Message); ok {
				messagesIDsChan <- m.ID
				offsetID = m.ID
			}
		}
		log.Printf("Buscados %d IDs de mensagens. Último ID: %d", len(messages.Messages), offsetID)
	}
}

func (c *Cloner) forwardMessages(ctx context.Context, wg *sync.WaitGroup, originPeer, destinyPeer tg.InputPeerClass, messagesIDsChan <-chan int) {
	defer wg.Done()
	ticker := time.NewTicker(3 * time.Second)
	defer ticker.Stop()

	for msgID := range messagesIDsChan {
		if ctx.Err() != nil {
			log.Println("Contexto cancelado, parando o encaminhamento.")
			return
		}
		<-ticker.C

		_, err := c.api.MessagesForwardMessages(ctx, &tg.MessagesForwardMessagesRequest{
			FromPeer:   originPeer,
			ID:         []int{msgID},
			ToPeer:     destinyPeer,
			DropAuthor: true,
			RandomID:   []int64{time.Now().UnixNano()},
		})
		if err != nil {
			log.Printf("Erro ao encaminhar mensagem ID %d: %v", msgID, err)
		} else {
			log.Printf("Mensagem ID %d encaminhada com sucesso.", msgID)
		}
	}
}

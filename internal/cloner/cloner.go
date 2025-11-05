package cloner

import (
	"context"
	"fmt"
	"log"

	"github.com/FolcloreX/teleclone/internal/config"
	"github.com/FolcloreX/teleclone/internal/storage"
	"github.com/gotd/td/telegram"
	"github.com/gotd/td/tg"
)

type Cloner struct {
	client  *telegram.Client
	api     *tg.Client
	cfg     *config.Config
	storage *storage.Manager
}

func New(client *telegram.Client, cfg *config.Config) (*Cloner, error) {
	api := tg.NewClient(client)
	storageManager, err := storage.NewManager(api)
	if err != nil {
		return nil, fmt.Errorf("não foi possível inicializar o gerenciador de armazenamento: %w", err)
	}
	return &Cloner{
		client:  client,
		api:     api,
		cfg:     cfg,
		storage: storageManager,
	}, nil
}

// resolveChannel it's an auxilary method that validates the destiny and origin channels.
func (c *Cloner) resolveChannel(ctx context.Context, channelID int64, channelName string) (*tg.Channel, error) {
	input := &tg.InputChannel{ChannelID: channelID}
	resolved, err := c.api.ChannelsGetChannels(ctx, []tg.InputChannelClass{input})
	if err != nil {
		return nil, fmt.Errorf("não foi possível resolver o canal de %s (ID: %d): %w", channelName, channelID, err)
	}

	chats, ok := resolved.(*tg.MessagesChats)
	if !ok {
		return nil, fmt.Errorf("tipo inesperado ao resolver canal de %s: %T", channelName, resolved)
	}
	if len(chats.Chats) == 0 {
		return nil, fmt.Errorf("nenhuma informação retornada para o canal de %s", channelName)
	}

	channel, ok := chats.Chats[0].(*tg.Channel)
	if !ok {
		return nil, fmt.Errorf("ID do canal de %s não é um canal, mas %T", channelName, chats.Chats[0])
	}

	return channel, nil
}

// Starts decides which pipeline to use according to the channel type.
func (c *Cloner) Start(ctx context.Context) error {
	log.Println("Resolvendo e verificando os grupos de origem e destino...")

	originChannel, err := c.resolveChannel(ctx, c.cfg.OriginChatID, "origem")
	if err != nil {
		return err
	}
	log.Printf("Canal de origem '%s' resolvido.", originChannel.Title)

	destinyChannel, err := c.resolveChannel(ctx, c.cfg.DestinyChatID, "destino")
	if err != nil {
		return err
	}

	log.Printf("Canal de destino '%s' resolvido.", destinyChannel.Title)

	originInputPeer := &tg.InputPeerChannel{
		ChannelID:  originChannel.ID,
		AccessHash: originChannel.AccessHash,
	}

	destinyInputPeer := &tg.InputPeerChannel{
		ChannelID:  destinyChannel.ID,
		AccessHash: destinyChannel.AccessHash,
	}

	if originChannel.Noforwards {
		log.Println("======================================================================")
		log.Printf("AVISO: Grupo de origem '%s' é PROTEGIDO. Iniciando modo de CÓPIA MANUAL.", originChannel.Title)
		log.Println("======================================================================")
		return c.runManualCopyPipeline(ctx, originInputPeer, destinyInputPeer)
	}

	log.Printf("Grupo de origem '%s' permite encaminhamento. Iniciando modo de ENCAMINHAMENTO.", originChannel.Title)
	return c.runForwardingPipeline(ctx, originInputPeer, destinyInputPeer)
}

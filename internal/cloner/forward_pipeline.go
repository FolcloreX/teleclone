package cloner

import (
	"context"
	"log"
	"sync"
	"time"

	"github.com/gotd/td/tg"
)

// runForwardingPipeline orquestra a busca e o encaminhamento.
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

// Get the message group history, put them in the ascending order then send to the forward channel
func (c *Cloner) fetchMessageIDs(ctx context.Context, wg *sync.WaitGroup, originPeer tg.InputPeerClass, messagesIDsChan chan<- int) {
	defer wg.Done()
	defer close(messagesIDsChan)

	log.Printf("Iniciando busca de IDs de mensagens...")
	offsetID := 0
	const limit = 100

	for {
		if ctx.Err() != nil {
			log.Println("Contexto cancelado, parando a busca.")
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

		// Store the ids in a temporary slice
		batchIDs := make([]int, 0, len(messages.Messages))
		for _, msg := range messages.Messages {
			if m, ok := msg.(*tg.Message); ok {
				batchIDs = append(batchIDs, m.ID)
				offsetID = m.ID
			}
		}

		// TODO: Find a better way of inverting the slice
		// I think that MessagesGetHistoryRequest, has something done with it
		for i, j := 0, len(batchIDs)-1; i < j; i, j = i+1, j-1 {
			batchIDs[i], batchIDs[j] = batchIDs[j], batchIDs[i]
		}

		// Send the ids in the correct order to the channel
		for _, id := range batchIDs {
			messagesIDsChan <- id
		}

		log.Printf("Buscados e ordenados %d IDs de mensagens. Último ID processado: %d", len(messages.Messages), offsetID)
	}
}

// forwardMessages receive the message ids and forward then.
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

		log.Printf("Encaminhando mensagem ID %d...", msgID)
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

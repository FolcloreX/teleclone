package cloner

import (
	"context"
	"log"
	"sync"
	"time"

	"github.com/gotd/td/tg"
)

// runManualCopyPipeline orquestra a busca e a recriação de mensagens.
func (c *Cloner) runManualCopyPipeline(ctx context.Context, originPeer, destinyPeer tg.InputPeerClass) error {
	var wg sync.WaitGroup
	wg.Add(2)
	messagesChan := make(chan *tg.Message, 100)

	log.Println("Iniciando pipeline de cópia manual...")
	go c.fetchFullMessages(ctx, &wg, originPeer, messagesChan)
	go c.processManualCopyMessages(ctx, &wg, destinyPeer, messagesChan)

	wg.Wait()
	log.Println("Processo de cópia manual concluído.")
	return nil
}

func (c *Cloner) fetchFullMessages(ctx context.Context, wg *sync.WaitGroup, originPeer tg.InputPeerClass, messagesChan chan<- *tg.Message) {
	defer wg.Done()
	defer close(messagesChan)

	log.Printf("Iniciando busca de mensagens completas...")
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

		// 1. Armazenar as mensagens em uma fatia temporária
		batchMessages := make([]*tg.Message, 0, len(messages.Messages))
		for _, msg := range messages.Messages {
			if m, ok := msg.(*tg.Message); ok {
				batchMessages = append(batchMessages, m)
				offsetID = m.ID
			}
		}

		// 2. Inverter a ordem da fatia
		for i, j := 0, len(batchMessages)-1; i < j; i, j = i+1, j-1 {
			batchMessages[i], batchMessages[j] = batchMessages[j], batchMessages[i]
		}

		// 3. Enviar as mensagens na ordem correta para o canal
		for _, msg := range batchMessages {
			messagesChan <- msg
		}

		log.Printf("Buscadas e ordenadas %d mensagens completas. Último ID processado: %d", len(messages.Messages), offsetID)
	}
}

// processManualCopyMessages recria as mensagens de texto e mídia no destino.
func (c *Cloner) processManualCopyMessages(ctx context.Context, wg *sync.WaitGroup, destinyPeer tg.InputPeerClass, messagesChan <-chan *tg.Message) {
	defer wg.Done()
	ticker := time.NewTicker(3 * time.Second)
	defer ticker.Stop()

	for msg := range messagesChan {
		if ctx.Err() != nil {
			log.Println("Contexto cancelado, parando a cópia.")
			return
		}
		<-ticker.C

		var err error
		if msg.Media != nil {
			log.Printf("Iniciando cópia de MÍDIA da msg ID %d...", msg.ID)

			log.Printf("Baixando mídia da msg ID %d...", msg.ID)
			filePath, errDownload := c.storage.DownloadMedia(ctx, msg.Media)
			if errDownload != nil {
				log.Printf("Falha ao baixar mídia da msg ID %d: %v. Pulando.", msg.ID, errDownload)
				continue
			}
			log.Printf("Mídia da msg ID %d baixada para: %s", msg.ID, filePath)

			log.Printf("Fazendo upload da mídia da msg ID %d...", msg.ID)
			inputMedia, errUpload := c.storage.UploadMedia(ctx, filePath)
			if errUpload != nil {
				log.Printf("Falha ao fazer upload da mídia da msg ID %d: %v. Pulando.", msg.ID, errUpload)
				if !c.cfg.KeepFiles {
					c.storage.Cleanup(filePath)
				}
				continue
			}

			log.Printf("Upload da mídia da msg ID %d concluído.", msg.ID)

			_, err = c.api.MessagesSendMedia(ctx, &tg.MessagesSendMediaRequest{
				Peer: destinyPeer, Media: inputMedia, Message: msg.Message, Entities: msg.Entities, RandomID: time.Now().UnixNano(),
			})

			if !c.cfg.KeepFiles {
				if err := c.storage.Cleanup(filePath); err != nil {
					log.Printf("AVISO: Falha ao limpar o arquivo temporário %s: %v", filePath, err)
				} else {
					log.Printf("Arquivo temporário %s limpo com sucesso.", filePath)
				}
			} else {
				log.Printf("Mantendo o arquivo temporário %s conforme configurado.", filePath)
			}

		} else if msg.Message != "" {
			log.Printf("Copiando manualmente texto da mensagem ID %d...", msg.ID)
			_, err = c.api.MessagesSendMessage(ctx, &tg.MessagesSendMessageRequest{
				Peer:     destinyPeer,
				Message:  msg.Message,
				Entities: msg.Entities,
				RandomID: time.Now().UnixNano(),
			})
		} else {
			log.Printf("Ignorando mensagem ID %d (vazia/serviço).", msg.ID)
			continue
		}

		if err != nil {
			log.Printf("Erro ao enviar cópia manual da mensagem ID %d: %v", msg.ID, err)
		} else {
			log.Printf("Cópia manual da mensagem ID %d enviada com sucesso.", msg.ID)
		}
	}
}

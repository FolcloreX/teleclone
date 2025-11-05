package main

import (
	"context"
	"fmt"
	"log"
	"os"
	"os/signal"

	"github.com/FolcloreX/teleclone/internal/cloner"
	"github.com/FolcloreX/teleclone/internal/config"
	"github.com/gotd/td/session"
	"github.com/gotd/td/telegram"
)

func main() {
	log.SetFlags(log.LstdFlags | log.Lshortfile)

	ctx, cancel := signal.NotifyContext(context.Background(), os.Interrupt)
	defer cancel()

	cfg, err := config.Load()
	if err != nil {
		log.Fatalf("Erro ao carregar configuração: %v", err)
	}

	client := telegram.NewClient(cfg.APIID, cfg.APIHash, telegram.Options{
		SessionStorage: &session.FileStorage{Path: "td_session"},
	})

	if err := client.Run(ctx, func(ctx context.Context) error {

		log.Println("Autenticação bem-sucedida!")

		// Starts the process of clonage
		clonerInstance := cloner.New(client, cfg)
		if err := clonerInstance.Start(ctx); err != nil {
			return fmt.Errorf("o processo de clonagem falhou: %w", err)
		}

		// After the clone process cancel the context
		log.Println("Aplicação encerrando de forma limpa.")
		cancel()
		return nil
	}); err != nil {
		log.Fatalf("A execução do cliente falhou: %v", err)
	}
}

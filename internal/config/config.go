package config

import (
	"fmt"
	"os"
	"strconv"

	"github.com/joho/godotenv"
)

type Config struct {
	APIID         int
	APIHash       string
	Phone         string
	Password      string
	OriginChatID  int64
	DestinyChatID int64
	KeepFiles     bool
}

func Load() (*Config, error) {
	if err := godotenv.Load(); err != nil {
		return nil, fmt.Errorf("erro ao carregar arquivo .env: %w", err)
	}

	apiID, err := strconv.Atoi(os.Getenv("API_ID"))
	if err != nil {
		return nil, fmt.Errorf("API_ID inválido no .env: %w", err)
	}

	originChatID, err := strconv.ParseInt(os.Getenv("ORIGIN_CHAT_ID"), 10, 64)
	if err != nil {
		return nil, fmt.Errorf("ORIGIN_CHAT_ID inválido: %w", err)
	}

	destinyChatID, err := strconv.ParseInt(os.Getenv("DESTINY_CHAT_ID"), 10, 64)
	if err != nil {
		return nil, fmt.Errorf("DESTINY_CHAT_ID inválido: %w", err)
	}

	keepFiles, err := strconv.ParseBool(os.Getenv("KEEP_DOWNLOADED_FILES"))
	if err != nil {
		// Se a flag estiver ausente ou mal formatada, assumimos 'false' por segurança.
		keepFiles = false
	}

	cfg := &Config{
		APIID:         apiID,
		APIHash:       os.Getenv("API_HASH"),
		Phone:         os.Getenv("PHONE_NUMBER"),
		Password:      os.Getenv("PASSWORD"),
		OriginChatID:  originChatID,
		DestinyChatID: destinyChatID,
		KeepFiles:     keepFiles,
	}

	if cfg.APIHash == "" || cfg.Phone == "" {
		return nil, fmt.Errorf("API_HASH e PHONE_NUMBER devem ser definidos no .env")
	}

	return cfg, nil
}

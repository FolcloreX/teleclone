package tgclient

import (
	"context"
	"errors"
	"fmt"

	"github.com/FolcloreX/teleclone/internal/config"
	"github.com/gotd/td/telegram/auth"
	"github.com/gotd/td/tg"
)

type authenticator struct {
	cfg *config.Config
}

func (a *authenticator) Phone(ctx context.Context) (string, error) {
	return a.cfg.Phone, nil
}

func (a *authenticator) Password(ctx context.Context) (string, error) {
	return a.cfg.Password, nil
}

func (a *authenticator) AcceptTermsOfService(ctx context.Context, tos tg.HelpTermsOfService) error {
	return nil
}

func (a *authenticator) SignUp(ctx context.Context) (auth.UserInfo, error) {
	return auth.UserInfo{}, errors.New("a criação de novas contas não é suportada")
}

func (a *authenticator) Code(ctx context.Context, sentCode *tg.AuthSentCode) (string, error) {
	fmt.Print("Digite o código de login que você recebeu: ")
	var code string
	if _, err := fmt.Scanln(&code); err != nil {
		return "", err
	}
	return code, nil
}

func NewAuthenticator(cfg *config.Config) auth.UserAuthenticator {
	return &authenticator{cfg: cfg}
}

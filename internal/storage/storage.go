package storage

import (
	"context"
	"fmt"
	"log"
	"os"
	"path/filepath"

	"github.com/gotd/td/telegram/downloader"
	"github.com/gotd/td/telegram/uploader"
	"github.com/gotd/td/tg"
)

type Manager struct {
	api        *tg.Client
	uploader   *uploader.Uploader
	downloader *downloader.Downloader
	tempDir    string
}

// NewManager creates a temp directory that will store the downloaded medias.
func NewManager(api *tg.Client) (*Manager, error) {
	tempDir, err := filepath.Abs(".temp_media")
	if err != nil {
		return nil, fmt.Errorf("não foi possível obter o caminho do diretório temporário: %w", err)
	}
	if err := os.RemoveAll(tempDir); err != nil {
		return nil, fmt.Errorf("não foi possível limpar o diretório temporário: %w", err)
	}
	if err := os.MkdirAll(tempDir, 0755); err != nil {
		return nil, fmt.Errorf("não foi possível criar o diretório temporário: %w", err)
	}

	log.Printf("Diretório temporário de mídias criado em: %s", tempDir)
	return &Manager{
		api:        api,
		uploader:   uploader.NewUploader(api),
		downloader: downloader.NewDownloader(),
		tempDir:    tempDir,
	}, nil
}

// DownloadMedia download the message media into the filesystem.
func (m *Manager) DownloadMedia(ctx context.Context, media tg.MessageMediaClass) (string, error) {
	var location tg.InputFileLocationClass
	var fileName string

	switch v := media.(type) {
	case *tg.MessageMediaPhoto:
		photo, ok := v.Photo.(*tg.Photo)
		if !ok {
			return "", fmt.Errorf("não foi possível obter o objeto da foto")
		}
		location = &tg.InputPhotoFileLocation{
			ID:            photo.ID,
			AccessHash:    photo.AccessHash,
			FileReference: photo.FileReference,
			ThumbSize:     "y",
		}
		fileName = fmt.Sprintf("%d.jpg", photo.ID)
	case *tg.MessageMediaDocument:
		doc, ok := v.Document.(*tg.Document)
		if !ok {
			return "", fmt.Errorf("não foi possível obter o objeto do documento")
		}
		location = &tg.InputDocumentFileLocation{
			ID:            doc.ID,
			AccessHash:    doc.AccessHash,
			FileReference: doc.FileReference,
		}
		for _, attr := range doc.Attributes {
			if f, ok := attr.(*tg.DocumentAttributeFilename); ok {
				fileName = f.FileName
				break
			}
		}
		if fileName == "" {
			fileName = fmt.Sprintf("doc_%d", doc.ID)
		}
	default:
		return "", fmt.Errorf("tipo de mídia não suportado para download: %T", v)
	}

	filePath := filepath.Join(m.tempDir, fileName)
	file, err := os.Create(filePath)
	if err != nil {
		return "", fmt.Errorf("não foi possível criar o arquivo temporário: %w", err)
	}
	defer file.Close()

	_, err = m.downloader.Download(m.api, location).Stream(ctx, file)
	if err != nil {
		return "", fmt.Errorf("falha no download: %w", err)
	}

	return filePath, nil
}

// UploadMedia uploads the downloaded media to telegram.
func (m *Manager) UploadMedia(ctx context.Context, filePath string) (tg.InputMediaClass, error) {
	f, err := os.Open(filePath)
	if err != nil {
		return nil, fmt.Errorf("não foi possível abrir o arquivo para upload: %w", err)
	}
	defer f.Close()

	// CORREÇÃO: Passamos o objeto do arquivo (f) para o uploader
	uploadedFile, err := m.uploader.Upload(ctx, uploader.NewUpload(filepath.Base(filePath), f, 0))
	if err != nil {
		return nil, fmt.Errorf("falha ao iniciar upload: %w", err)
	}

	return &tg.InputMediaUploadedDocument{
		File:     uploadedFile,
		MimeType: "application/octet-stream",
		Attributes: []tg.DocumentAttributeClass{
			&tg.DocumentAttributeFilename{
				FileName: filepath.Base(filePath),
			},
		},
	}, nil
}

// Remove all temporary files
func (m *Manager) Cleanup(filePath string) error {
	return os.Remove(filePath)
}

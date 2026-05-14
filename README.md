# Audio Converter API

API de conversion audio avec Docker, FastAPI et FFmpeg.

## Fonctionnalités

- **Conversion multi-format** : mp3, ogg, wav, flac, aac, m4a
- **Stockage propre** : fichiers convertis dans `./tmp/`
- **Hash MD5** : vérification d'intégrité des fichiers
- **Monitoring** : statistiques via `/convert/metrics`
- **Auto-cleanup** : suppression automatique des fichiers > 12h
- **Swagger UI** : documentation interactive à `/docs`

## Installation

```bash
# Build et lancement
docker build -t audio-converter .
docker run -d -p 8000:8000 -v $(pwd)/tmp:/tmp/convert --name audio-converter audio-converter

# Ou avec docker-compose
docker-compose up -d --build
```

## Endpoints

| Méthode | Route | Description |
|---------|-------|-------------|
| POST | `/convert/upload/{input_format}?output_format={fmt}` | Upload + conversion |
| GET | `/convert/{job_id}` | Statut du job |
| GET | `/convert/{job_id}/download` | Télécharger le fichier converti |
| POST | `/convert/{job_id}/download-delete` | Télécharger + vérifier hash + supprimer |
| DELETE | `/convert/{job_id}` | Supprimer le job |
| GET | `/convert/metrics` | Statistiques (jobs, cleanup) |

## Utilisation

### Upload et conversion

```bash
# Upload mp3 → ogg
curl -X POST "http://localhost:8000/convert/upload/mp3?output_format=ogg" \
  -F "file=@audio.mp3"
```

**Réponse :**
```json
{
  "job_id": "abc123...",
  "input_hash": "f8e5497a0f94e116f75143a93c86c008",
  "message": "File uploaded. Conversion mp3 → ogg started."
}
```

### Statut et download

```bash
# Vérifier le statut
curl http://localhost:8000/convert/{job_id}

# Télécharger
curl -O http://localhost:8000/convert/{job_id}/download

# Supprimer
curl -X DELETE http://localhost:8000/convert/{job_id}
```

### Vérification hash avant suppression

```bash
# Après téléchargement local, vérifier le hash MD5
HASH=$(md5sum downloaded.ogg | awk '{print $1}')

# Supprimer avec vérification
curl -X POST "http://localhost:8000/convert/{job_id}/download-delete" \
  -H "X-Content-Hash: $HASH"
```

**Réponse si succès :**
```json
{"success": true, "message": "File downloaded and deleted successfully.", "hash_verified": true}
```

**Réponse si hash mismatch :**
```json
{"success": false, "message": "Hash mismatch! File NOT deleted.", "job_id": "...", "hash_verified": false}
```

## Monitoring

```bash
curl http://localhost:8000/convert/metrics
```

**Réponse :**
```json
{
  "jobs_created": 15,
  "jobs_completed": 12,
  "jobs_failed": 1,
  "jobs_pending": 2,
  "total_bytes_processed": 52485760,
  "conversions_by_format": {
    "mp3": 3,
    "ogg": 5,
    "wav": 4
  },
  "cleanup_runs": 24,
  "cleanup_files_removed": 8,
  "cleanup_bytes_freed": 15728640
}
```

## Formats supportés

| Format | Codec | Qualité |
|--------|-------|---------|
| mp3 | libmp3lame | ~192 kbps |
| ogg | libvorbis | ~96 kbps |
| wav | pcm_s16le | lossless |
| flac | flac | lossless |
| aac | aac | ~128 kbps |
| m4a | aac | ~128 kbps |

## Structure des fichiers

```
tmp/
├── input/                    (fichiers sources temporaires)
└── {nom}_{hash8}.{fmt}      (fichiers convertis)
```

## Nettoyage automatique

- Intervalle : toutes les heures
- Age max : 12 heures
- Logs : visibles dans les logs du container

## Développement

```bash
# Tests unitaires
python -m pytest tests/ -v

# Mode développement
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## Swagger UI

Accessible sur : http://localhost:8000/docstest

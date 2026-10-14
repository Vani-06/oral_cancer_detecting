# oral cancer deep learning - backend API

---

# Base URL

```
http://localhost:8000
```

---

# Health Check

Verifies that the backend is running.

### Endpoint

```http
GET /
```

### Response

```json
{
    "status": "healthy"
}
```

---

# Upload Image for Prediction

Uploads an oral lesion image to the backend. Currently, the backend only stores the image and returns a success response. ML inference will be integrated later.

### Endpoint

```http
POST /predict
```

### Content-Type

```
multipart/form-data
```

### Request Body

| Field | Type | Required | Description |
|--------|------|----------|-------------|
| file | Image File | Yes | Oral lesion image |

### Current Response

```json
{
    "filename": "3df9e5dc-f07b-4f66-bd72.jpg",
    "status": "uploaded successfully"
}
```

### Planned Response

```json
{
    "prediction_id": 1,
    "prediction": "Cancer",
    "confidence": 0.96,
    "heatmap_url": "/predictions/1/heatmap",
    "pdf_url": "/reports/1.pdf"
}
```

> **Frontend Note:** Design the prediction results page according to the **planned response**, even though the backend currently returns only the filename and status.

---

# Current Backend Features

- FastAPI project initialized
- Swagger/OpenAPI documentation enabled
- Health check endpoint
- Image upload endpoint
- Images saved locally on the server

---

# Planned API Endpoints

## Authentication

```http
POST /register
POST /login
GET /me
```

---

## Predictions

```http
POST /predict
GET /predictions
GET /predictions/{id}
```

---

## Reports

```http
GET /reports/{prediction_id}
```

Downloads the generated PDF report.

---

# Planned Response Models

## Prediction

```json
{
    "prediction_id": 1,
    "prediction": "Cancer",
    "confidence": 0.96,
    "heatmap_url": "/predictions/1/heatmap",
    "pdf_url": "/reports/1.pdf"
}
```

---

## Prediction History

```json
[
    {
        "prediction_id": 1,
        "prediction": "Cancer",
        "confidence": 0.96,
        "created_at": "2026-08-03T18:25:41Z"
    },
    {
        "prediction_id": 2,
        "prediction": "Non-Cancer",
        "confidence": 0.88,
        "created_at": "2026-08-04T10:11:02Z"
    }
]
```

---

# Frontend Pages

| Page | API |
|------|-----|
| Login | `/login` |
| Dashboard | `/predictions` |
| Upload Image | `/predict` |
| Prediction Result | `/predict` |
| Prediction History | `/predictions` |
| Report Download | `/reports/{id}` |

---

# Current Project Structure

```text
backend/
│
├── app/
│   ├── __init__.py
│   ├── main.py
│   │
│   ├── routers/
│   │   ├── __init__.py
│   │   └── prediction.py
│   │
│   └── uploads/
│
└── requirements.txt
```

---

# Upcoming Features

- JWT Authentication
- PostgreSQL Database
- Prediction History
- Machine Learning Inference
- Explainability (Grad-CAM)
- PDF Report Generation
- Cloud Deployment

---

# Notes for Frontend Development

- Use **`multipart/form-data`** when uploading images.
- Assume authentication endpoints will be available soon.
- Design the prediction page based on the **planned response model**.
- Prediction history should display:
  - Uploaded image (thumbnail)
  - Prediction
  - Confidence
  - Date & Time
  - View Report button

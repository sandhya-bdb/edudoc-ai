# EduDoc AI: Product Requirements Document

## 1. Product Overview
EduDoc AI is a multimodal, automated document classification system designed specifically for the education sector. It classifies documents like Transcripts, Certificates, Student IDs, and Admission Letters with high accuracy. This replaces manual sorting work in admissions and administrative offices.

## 2. Three-Stage Cascade Pipeline Architecture
To optimize for cost, latency, and accuracy, the system processes documents through three stages:

**STAGE 1: REGEX (Free, Instant)**
- Uses filename patterns to classify common documents.
- Examples: 'transcript_*.png' -> Transcripts, 'cert_*.png' -> Certificates.

**STAGE 2: OCR + KEYWORDS (Free, ~1-2s)**
- Extracts text from the image using local OCR and matches against a set of educational keywords.
- Examples: 'University', 'College', 'Transcript' -> Educational Documents.

**STAGE 3: MULTIMODAL LLM (API Call)**
- For documents that fail the first two fast stages, the image and text are sent to Google Gemma 4 31B IT.
- This accurately classifies complex layouts or unpredictable documents into strict categories.

## 3. Why this approach?
- Reduces LLM API calls by 30-40%.
- Lower operational costs and faster average response times.
- High accuracy with fallback intelligence.
- Fully traceable using LangSmith.

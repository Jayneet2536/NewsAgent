# 📰 NewsAgent

**NewsAgent** is an AI-powered autonomous news aggregation and research platform. Ask a question in plain English, and the system leverages a multi-stage AI agent workflow to research, draft, and fact-check a curated markdown digest—delivered live to the browser via Server-Sent Events (SSE).

![NewsAgent Workflow](https://img.shields.io/badge/LangGraph-Autonomous_Agents-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-Backend-009688)
![Nginx](https://img.shields.io/badge/Nginx-Reverse_Proxy-009609)
![Docker](https://img.shields.io/badge/Docker-Containerized-2496ED)

---

## 🏗️ Architecture & Agent Workflow

The core of NewsAgent is a **LangGraph-based state machine** operating in the backend. When a user submits a query, the agent orchestrates four specialized nodes in sequence:

1. 🗺️ **Planner Node:** Analyzes the user's plain-English query, extracts core topics, and designs a multi-step search plan.
2. 🔍 **Researcher Node:** Executes the plan using the Tavily Search API. It concurrently fetches articles, parses the raw HTML text, and aggregates the data into the state.
3. ✍️ **Writer Node:** Takes the aggregated research (titles, URLs, snippets, and parsed text) and synthesizes a structured, easy-to-read Markdown digest.
4. ✅ **Verifier Node:** Acts as a strict factual auditor. It cross-references the generated digest against the original fetched articles, scoring the output out of 100 and appending a list of any hallucinated or unverified claims.

The entire process is streamed in real-time to a **Vanilla HTML/JS frontend** using an asynchronous **Server-Sent Events (SSE)** connection, keeping the user updated on exactly which node is currently running.

---

## 🚀 Setup & Installation Instructions

The application is fully containerized with Docker, separating the frontend (Nginx) and backend (FastAPI) environments.

### 1. Prerequisites
- [Docker](https://docs.docker.com/get-docker/) & Docker Compose installed.
- API Keys for the AI services:
  - **Groq API Key** (for fast Llama 3 inference).
  - **Tavily API Key** (for agentic web search).

### 2. Environment Configuration
Create a `.env` file inside the `backend/` directory:
```bash
# backend/.env
GROQ_API_KEY=your_groq_key_here
TAVILY_API_KEY=your_tavily_key_here
MODEL_NAME=llama3-8b-8192
DEBUG=true
FRONTEND_ORIGIN=http://localhost
```

### 3. Build and Run
From the root of the project, run the following command to build the images and start the containers in detached mode:
```bash
docker compose up --build -d
```

### 4. ⚠️ How to Open the Frontend
To avoid CORS (Cross-Origin Resource Sharing) security errors, you **must access the frontend via the Nginx web server**.

❌ **DO NOT:** Double-click `index.html` to open it in your browser (which resolves to `file:///...`). The browser will block the API requests.

✅ **DO:** Open your browser and navigate to:
👉 **[http://localhost](http://localhost)**

The Nginx proxy will correctly route frontend requests and securely proxy backend SSE API calls to FastAPI.

---

## 📈 Resume Points & Technical Highlights

If you're including this project on your resume, here are several strong, metrics-driven bullet points you can use to highlight your engineering work:

* **AI Agent Orchestration:** Architected a full-stack AI news aggregation platform using FastAPI and LangGraph, orchestrating a 4-stage autonomous agent pipeline (Planner, Researcher, Writer, Verifier) to generate fact-checked digests from plain-text queries.
* **Real-time Streaming Architecture:** Implemented a resilient Server-Sent Events (SSE) streaming architecture with Nginx reverse proxying, maintaining active connections via asynchronous heartbeats during multi-minute LLM inference cycles to eliminate timeout disconnects.
* **Automated Fact-Checking & RAG:** Integrated Groq's high-speed inference (Llama 3) and Tavily's search API, mitigating hallucinations by engineering a dedicated Verifier node that scores generated content against source materials to ensure 100% data provenance.
* **Containerized Microservices:** Containerized the application using Docker and Docker Compose, successfully decoupling a lightweight Vanilla JS frontend from a Python backend, establishing a secure reverse-proxy configuration that bypassed strict browser CORS policies.

---

## 📂 Repository Structure

```text
.
├── docker-compose.yml       # Orchestrates frontend (Nginx) and backend (FastAPI)
├── backend/
│   ├── .env                 # API Keys and configuration (Not checked into Git)
│   ├── Dockerfile           # Python 3.12 slim container setup
│   ├── requirements.txt     # Python dependencies
│   └── src/                 # Backend source code
│       ├── api/             # FastAPI routers, schemas, and SSE generator
│       ├── graph/           # LangGraph workflow definition
│       ├── nodes/           # Planner, Researcher, Writer, and Verifier logic
│       ├── tools/           # Tavily search and web-fetching utilities
│       └── prompts/         # System prompts for the LLM
└── frontend/
    ├── Dockerfile           # Nginx alpine container setup
    ├── index.html           # Beautiful, glassmorphism UI (Vanilla HTML/JS/CSS)
    └── nginx/
        └── default.conf     # Nginx config with SSE proxy buffering optimizations
```

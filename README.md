# ADK Voice Assistant

This is a hybrid Next.js + FastAPI application for running a Google ADK voice assistant.

## Project Structure

- `app/` - Python FastAPI backend that integrates with Google ADK
- `frontend/` - Next.js frontend application

## Setup

### Prerequisites

- Python 3.8+ with pip
- Node.js 18+ with npm
- Google API key for using the Gemini model

### Backend Setup

1. Create and activate a virtual environment:

```bash
# Create virtual environment
python -m venv .venv

# Activate it on Windows
.venv\Scripts\activate

# Or on macOS/Linux
source .venv/bin/activate
```

2. Install the Python dependencies:

```bash
pip install -r requirements.txt
```

3. Set up your Google API key:

```bash
# Create a .env file
echo "GOOGLE_API_KEY=your_api_key_here" > .env
```

4. Start the FastAPI backend:

```bash
cd app
uvicorn main:app --reload
```

The backend will be available at http://localhost:8000

### Frontend Setup

1. Install the Node.js dependencies:

```bash
cd frontend
npm install
```

2. Start the Next.js development server:

```bash
npm run dev
```

The frontend will be available at http://localhost:3000

## Usage

1. Open your browser to http://localhost:3000
2. Use the text input to chat with the assistant
3. Toggle audio mode to use voice input/output (requires microphone access)

## Technical Details

- The frontend uses Next.js with React and TypeScript
- WebSocket communication is used for real-time messaging
- The backend is built with FastAPI and Google's ADK
- Audio capture and playback is handled in the browser

## Development

- Frontend code is in `frontend/src/`
- Backend code is in `app/` 

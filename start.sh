#!/bin/bash

# Start the FastAPI backend
echo "Starting FastAPI backend..."
cd app
uvicorn main:app --reload &
BACKEND_PID=$!

# Wait a moment to ensure backend is running
sleep 2

# Start the Next.js frontend
echo "Starting Next.js frontend..."
cd ../frontend
npm run dev &
FRONTEND_PID=$!

# Handle cleanup on exit
trap 'kill $BACKEND_PID $FRONTEND_PID; exit' INT TERM EXIT

# Keep script running until Ctrl+C
echo "Both services are running. Press Ctrl+C to stop."
wait 

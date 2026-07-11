#!/bin/bash
echo "Starting Rue by MG&CO..."
echo ""
echo "Starting backend..."
cd backend && uvicorn main:app --reload --port 8000 &
echo "Starting frontend..."
cd ../frontend && npm run dev &
echo ""
echo "Rue is running."
echo "Backend:  http://localhost:8000"
echo "Frontend: http://localhost:3000"
echo ""
echo "Open http://localhost:3000 to talk to Rue."

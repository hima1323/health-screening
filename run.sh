#!/usr/bin/env bash
# Starts the API and the client together. Ctrl+C stops both.
#
#   Port 4000  API     server/  (Express; PORT in server/.env)
#   Port 5173  Client  client/  (Vite; proxies /api -> http://localhost:4000)
#
# Open http://localhost:5173 in the browser. MongoDB comes from MONGODB_URI in server/.env.
set -e
cd "$(dirname "$0")"

[ -f server/.env ] || { echo "server/.env missing: cp server/.env.example server/.env and fill it in"; exit 1; }
[ -d server/node_modules ] || (cd server && npm install)
[ -d client/node_modules ] || (cd client && npm install)

trap 'kill 0' EXIT

echo "API     -> http://localhost:4000"
echo "Client  -> http://localhost:5173  (open this)"

(cd server && npm start) &
(cd client && npm run dev) &
wait

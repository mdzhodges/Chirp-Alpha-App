# Chirp Backend (Spring Boot)

## Prereqs
- Java 21+ (JDK)

## Run
- `./mvnw spring-boot:run`
- Backend runs on `http://localhost:8080`

## API
- `GET /api/health`
- `GET /api/chirps`
- `POST /api/chirps` with JSON:
  - `{ "message": "hello", "author": "matt" }`
- `GET /api/ticker?symbol=AAPL`
- `GET /api/ticker/AAPL`
- `POST /api/ticker` with JSON:
  - `{ "symbol": "AAPL" }`

## Dashboard
- `GET /dashboard` (simple page to fetch and display ticker metrics)

## Frontend dev (Vite)
The frontend is configured to proxy `/api` to `http://localhost:8080`, so the UI can call `/api/...` without extra CORS setup.

### Needed packages
Maven, java-21-openjdk-devel

Then run: 
 mvn wrapper:wrapper
 
To run:
./mvnw spring-boot:run

 
Sample Curl: 
curl -X POST "http://localhost:8080/api/chirps" \
    -H "Content-Type: application/json" \
    -d '{"message":"hello from the frontend","author":"matt"}'

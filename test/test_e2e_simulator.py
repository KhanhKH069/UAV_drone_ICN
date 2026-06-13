import argparse
import asyncio
import json
import sys
import httpx
import websockets

# Configuration default values
DEFAULT_GATEWAY_URL = "http://localhost:8056"
DEFAULT_CLIENT_ID = "drone-simulator"
DEFAULT_CLIENT_SECRET = "drone-secret"


async def authenticate(gateway_url, client_id, client_secret):
    """Fetches JWT token from Gateway auth endpoint."""
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.post(
                f"{gateway_url}/auth/token",
                json={"client_id": client_id, "client_secret": client_secret},
                timeout=10.0,
            )
            if resp.status_code == 200:
                token = resp.json().get("access_token")
                print(f"[✔] Authentication successful! Token: {token[:15]}...")
                return token
            else:
                print(f"[✘] Authentication failed: HTTP {resp.status_code} - {resp.text}")
                return None
        except Exception as e:
            print(f"[✘] Failed to connect to auth gateway: {e}")
            return None


async def run_simulator(gateway_url, token, drone_id, lang):
    """Connects to the gateway WebSocket, sends telemetry, and simulates end-of-speech."""
    # Convert http:// to ws://
    ws_url = gateway_url.replace("http://", "ws://").replace("https://", "wss://")
    ws_endpoint = f"{ws_url}/drone/stream?drone_id={drone_id}&lang={lang}"

    print(f"Connecting to Gateway WebSocket: {ws_endpoint}...")
    try:
        async with websockets.connect(ws_endpoint) as ws:
            print("[✔] WebSocket connection established.")

            # Send Auth event
            auth_payload = {"event": "auth", "token": token}
            await ws.send(json.dumps(auth_payload))
            print("Sent auth token.")

            # Send mock telemetry
            telemetry_payload = {
                "event": "telemetry",
                "data": {
                    "battery": 95,
                    "altitude": 10.4,
                    "latitude": 21.0285,
                    "longitude": 105.8542,
                },
            }
            await asyncio.sleep(1.0)
            await ws.send(json.dumps(telemetry_payload))
            print("Sent telemetry data.")

            # Start listener task to receive response messages
            async def receive_messages():
                try:
                    async for message in ws:
                        data = json.loads(message)
                        print("\n[Received from Gateway]:")
                        print(json.dumps(data, indent=2, ensure_ascii=False))
                except websockets.exceptions.ConnectionClosed:
                    print("\nConnection closed by gateway.")
                except Exception as e:
                    print(f"\nError receiving: {e}")

            recv_task = asyncio.create_task(receive_messages())

            # Simulate sending binary audio (3 seconds of silence) to construct buffer
            print("Sending 3 seconds of dummy audio buffer (silence)...")
            sample_rate = 16000
            channels = 1
            bytes_per_sample = 2
            seconds = 3
            silence_bytes = bytes(sample_rate * channels * bytes_per_sample * seconds)

            # Send in chunks of 0.5s
            chunk_size = sample_rate * channels * bytes_per_sample // 2
            for i in range(0, len(silence_bytes), chunk_size):
                chunk = silence_bytes[i : i + chunk_size]
                await ws.send(chunk)
                await asyncio.sleep(0.5)

            print("Triggering speech recognition endpoint...")
            endpoint_payload = {"event": "endpoint"}
            await ws.send(json.dumps(endpoint_payload))

            # Wait a few seconds to capture response broadcast
            await asyncio.sleep(5.0)
            recv_task.cancel()

    except Exception as e:
        print(f"[✘] WebSocket session error: {e}")


def main():
    parser = argparse.ArgumentParser(
        description="Paraline MSAgent E2E Integration Simulator"
    )
    parser.add_argument(
        "--gateway-url", default=DEFAULT_GATEWAY_URL, help="Gateway base HTTP URL"
    )
    parser.add_argument("--client-id", default=DEFAULT_CLIENT_ID, help="Auth client ID")
    parser.add_argument(
        "--client-secret", default=DEFAULT_CLIENT_SECRET, help="Auth client secret"
    )
    parser.add_argument("--drone-id", default="drone-sim-007", help="Drone Identifier")
    parser.add_argument(
        "--lang",
        default="en",
        choices=["en", "vi", "ja"],
        help="Speech input language",
    )

    args = parser.parse_args()

    print("==========================================================")
    print("      PARALINE MSAGENT E2E SIMULATOR")
    print("==========================================================")

    token = asyncio.run(
        authenticate(args.gateway_url, args.client_id, args.client_secret)
    )
    if not token:
        print("[✘] Simulator aborted due to authentication failure.")
        sys.exit(1)

    asyncio.run(run_simulator(args.gateway_url, token, args.drone_id, args.lang))
    print("==========================================================")


if __name__ == "__main__":
    main()

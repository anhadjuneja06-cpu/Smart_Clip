import os
import dotenv
from deepgram import DeepgramClient

dotenv.load_dotenv()

def test_dg():
    api_key = os.getenv("DEEPGRAM_API_KEY")
    if not api_key:
        print("No API Key found in .env")
        return

    try:
        # User's code used api_key=dg_api_key
        client = DeepgramClient(api_key=api_key)
        print("Client initialized:", client)
        
        # Check for listen.v1.media.transcribe_file as used in transcribe_audio.py
        print("Listen attr:", hasattr(client, 'listen'))
        print("Listen.v1 attr:", hasattr(client.listen, 'v1'))
        print("Listen.v1.media attr:", hasattr(client.listen.v1, 'media'))
        print("Transcribe method exists:", hasattr(client.listen.v1.media, 'transcribe_file'))
        
    except Exception as e:
        print(f"Test failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_dg()

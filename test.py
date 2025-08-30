from dulayni import DulayniClient
import os

from dotenv import load_dotenv

_ = load_dotenv()


if __name__ == '__main__':
    # Set API key from environment variable
    api_key = os.getenv("DULAYNI_API_KEY")
    client = DulayniClient(
        dulayni_api_key=api_key,
        api_url="http://0.0.0.0:8002",
        model="gpt-4o-mini",
        agent_type="deep_react",
        thread_id="test-1234",
        system_prompt="You are a helpful assistant specialized in mathematics."
    )

    # Conversation with thread continuity
    response1 = client.query("Hello")
    print(response1)


import asyncio
from app.agent.manus import Manus

async def main():
    print("Initializing Manus agent for testing...")
    try:
        # Create an instance of the Manus agent
        agent = await Manus.create()

        # 1. Verify the system prompt
        print("\n" + "="*50)
        print("VERIFYING SYSTEM PROMPT")
        print("="*50)
        # To keep the output clean, we'll check if the prompt starts and ends correctly
        # and print a snippet.
        prompt_snippet = agent.system_prompt[:200] + "..." + agent.system_prompt[-200:]
        print(f"System prompt loaded successfully. Snippet:\n{prompt_snippet}")
        if "<shell_rules>" in agent.system_prompt:
            print("\n[SUCCESS] New system prompt is correctly loaded.")
        else:
            print("\n[FAILURE] System prompt does not seem to be the new version.")


        # 2. Verify the available tools
        print("\n" + "="*50)
        print("VERIFYING AVAILABLE TOOLS")
        print("="*50)
        tool_names = [tool.name for tool in agent.available_tools.tools]
        print("Available tools:")
        for name in tool_names:
            print(f"- {name}")

        # Check for one of the new tools
        if "message_notify_user" in tool_names:
            print("\n[SUCCESS] New tools are correctly loaded.")
        else:
            print("\n[FAILURE] New tools are not loaded.")

        await agent.cleanup()
        print("\nAgent cleanup successful.")

    except Exception as e:
        print(f"\nAn error occurred during the test: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())

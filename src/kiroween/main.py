"""Application entry point for the Kiroween Slack agent."""

import asyncio
import sys

from kiroween.agenda.tools import get_agenda_tools
from kiroween.agent.graph import build_graph, run_agent
from kiroween.config import get_settings
from kiroween.mcp.client import get_mcp_manager
from kiroween.utils.logging import get_logger, setup_logging

logger = get_logger(__name__)


async def initialize_agent():
    """Initialize the agent with all tools.

    Returns:
        Tuple of (graph, mcp_manager) ready for use.
    """
    settings = get_settings()
    setup_logging(log_level=settings.log_level)

    logger.info("initializing_agent", env=settings.app_env)

    # Get agenda tools
    agenda_tools = get_agenda_tools()
    logger.info("agenda_tools_loaded", count=len(agenda_tools))

    # Connect to Slack MCP and get tools
    mcp_manager = get_mcp_manager()
    await mcp_manager.connect()
    slack_tools = mcp_manager.get_slack_tools()
    logger.info("slack_tools_loaded", count=len(slack_tools))

    # Combine all tools
    all_tools = agenda_tools + slack_tools

    # Build the graph
    graph = build_graph(all_tools)

    return graph, mcp_manager


async def run_interactive():
    """Run the agent in interactive CLI mode."""
    print("Kiroween Slack Agent")
    print("=" * 40)
    print("Type your request and press Enter.")
    print("Type 'quit' or 'exit' to stop.")
    print("=" * 40)
    print()

    try:
        graph, mcp_manager = await initialize_agent()

        while True:
            try:
                user_input = input("You: ").strip()

                if not user_input:
                    continue

                if user_input.lower() in ("quit", "exit", "q"):
                    print("\nGoodbye!")
                    break

                # Run the agent
                final_state = await run_agent(graph, user_input)

                # Get the response
                messages = final_state.get("messages", [])
                if messages:
                    last_message = messages[-1]
                    response = (
                        last_message.content
                        if hasattr(last_message, "content")
                        else str(last_message)
                    )
                    print(f"\nAgent: {response}\n")
                else:
                    print("\nAgent: (No response generated)\n")

            except KeyboardInterrupt:
                print("\n\nInterrupted. Goodbye!")
                break
            except Exception as e:
                logger.error("run_error", error=str(e))
                print(f"\nError: {e}\n")

    finally:
        # Cleanup
        await mcp_manager.disconnect()


async def run_single(user_input: str) -> str:
    """Run the agent with a single input.

    Args:
        user_input: The user's message.

    Returns:
        The agent's response as a string.
    """
    graph, mcp_manager = await initialize_agent()

    try:
        final_state = await run_agent(graph, user_input)

        messages = final_state.get("messages", [])
        if messages:
            last_message = messages[-1]
            return (
                last_message.content
                if hasattr(last_message, "content")
                else str(last_message)
            )
        return "(No response generated)"

    finally:
        await mcp_manager.disconnect()


def main():
    """Main entry point."""
    settings = get_settings()
    setup_logging(log_level=settings.log_level)

    if len(sys.argv) > 1:
        # Run with command line input
        user_input = " ".join(sys.argv[1:])
        response = asyncio.run(run_single(user_input))
        print(response)
    else:
        # Run in interactive mode
        asyncio.run(run_interactive())


if __name__ == "__main__":
    main()

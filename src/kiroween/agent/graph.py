"""Main LangGraph StateGraph definition."""

from langchain_core.tools import BaseTool
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition

from kiroween.agent.edges import route_by_intent
from kiroween.agent.nodes.extractor import extractor_node
from kiroween.agent.nodes.responder import create_responder_node
from kiroween.agent.nodes.router import router_node
from kiroween.agent.nodes.searcher import searcher_node
from kiroween.agent.nodes.summarizer import summarizer_node
from kiroween.agent.nodes.tracker import tracker_node
from kiroween.agent.state import AgentState
from kiroween.utils.logging import get_logger

logger = get_logger(__name__)


def build_graph(tools: list[BaseTool]) -> StateGraph:
    """Build the LangGraph StateGraph for the Slack agent.

    Args:
        tools: List of all available tools (Slack MCP + Agenda).

    Returns:
        Compiled StateGraph ready for invocation.

    Graph structure:
        START → router → [summarizer|searcher|tracker|extractor|responder]
                              ↓           ↓          ↓           ↓
                         responder ← ← ← ← ← ← ← ← ← ← ← ← ← ← ← ←
                              ↓
                         tools_condition
                              ↓
                    [tools → responder] or END
    """
    logger.info("building_graph", tools_count=len(tools))

    # Create the graph with our state schema
    builder = StateGraph(AgentState)

    # Create responder node with tools bound
    responder = create_responder_node(tools)

    # Add all nodes
    builder.add_node("router", router_node)
    builder.add_node("summarizer", summarizer_node)
    builder.add_node("searcher", searcher_node)
    builder.add_node("tracker", tracker_node)
    builder.add_node("extractor", extractor_node)
    builder.add_node("responder", responder)
    builder.add_node("tools", ToolNode(tools))

    # Entry point: start with router
    builder.add_edge(START, "router")

    # Conditional routing from router based on intent
    builder.add_conditional_edges(
        "router",
        route_by_intent,
        {
            "summarizer": "summarizer",
            "searcher": "searcher",
            "tracker": "tracker",
            "extractor": "extractor",
            "responder": "responder",
        },
    )

    # All processing nodes lead to responder
    builder.add_edge("summarizer", "responder")
    builder.add_edge("searcher", "responder")
    builder.add_edge("tracker", "responder")
    builder.add_edge("extractor", "responder")

    # Responder can call tools or finish
    builder.add_conditional_edges(
        "responder",
        tools_condition,
        {
            "tools": "tools",
            END: END,
        },
    )

    # After tools, return to responder for more processing
    builder.add_edge("tools", "responder")

    # Compile the graph
    graph = builder.compile()

    logger.info("graph_built")
    return graph


async def run_agent(
    graph: StateGraph,
    user_input: str,
    initial_state: AgentState | None = None,
) -> AgentState:
    """Run the agent with a user input.

    Args:
        graph: Compiled StateGraph.
        user_input: The user's message.
        initial_state: Optional initial state (for continuing conversations).

    Returns:
        Final agent state after processing.
    """
    from langchain_core.messages import HumanMessage

    from kiroween.agent.state import create_initial_state

    logger.info("running_agent", input_preview=user_input[:100])

    # Create or update state
    if initial_state is None:
        state = create_initial_state()
    else:
        state = initial_state

    # Add user message
    state["messages"] = [HumanMessage(content=user_input)]

    # Run the graph
    final_state = await graph.ainvoke(state)

    logger.info(
        "agent_completed",
        message_count=len(final_state.get("messages", [])),
        has_error=bool(final_state.get("error")),
    )

    return final_state

import logging
import operator
from dataclasses import dataclass
from typing import TypedDict, Annotated

from langchain.prompts import Prompt
from langchain_core.messages import SystemMessage
from langchain_core.tools import tool
from langgraph.graph import MessagesState
from langgraph.runtime import Runtime

from model.model import model
from persona.agent import agent_analyze_and_classify_prompt, agent_courtesy_query_prompt, agent_personal_query_prompt, \
    agent_generate_message_prompt
from persona.me import me_analyze_and_classify_prompt, me_courtesy_query_prompt, me_personal_query_prompt, \
    me_generate_message_prompt
from stores.store import get_retriever

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
logger.setLevel(level=logging.INFO)


class ContextSchema(TypedDict):
    """Context parameters for the agent.

    Set these when creating assistants OR when invoking the graph.
    See: https://langchain-ai.github.io/langgraph/cloud/how-tos/configuration_cloud/
    """
    ctr_th: int
    personal_ctr_th: int
    courtesy_ctr_th: int
    persona: str
    name: str
    loggedin_name: str


@dataclass
class BioMessageState(MessagesState):
    ctr: Annotated[int, operator.add] = 0
    personal_ctr: Annotated[int, operator.add] = 0
    courtesy_ctr: Annotated[int, operator.add] = 0


@tool(response_format="content_and_artifact")
def retrieve(query: str):
    """Retrieve information related to a query asking for professional information"""
    # print("INSIDE TOOL")

    # retrieved_docs = vector_store.similarity_search(query, k=2)
    retrieved_docs = get_retriever().invoke(query)
    serialized = "\n\n".join(
        f"Source: {doc.metadata}\nContent: {doc.page_content}"
        for doc in retrieved_docs
    )
    return serialized, retrieved_docs


# Step 1: Generate an AIMessage that may include a tool-call to be sent.
def query_or_respond(state: BioMessageState, context: Runtime[ContextSchema]) -> MessagesState:
    """Generate tool call for retrieval or respond."""
    llm_with_tools = model.bind_tools([retrieve], tool_choice="retrieve")
    response = llm_with_tools.invoke(state["messages"])
    # MessagesState appends messages to state instead of overwriting
    # print(f"response content in query_or_respond is {response.content}")
    return response
    # return {"messages": [response]}


def analyze_and_classify(state: BioMessageState, runtime: Runtime[ContextSchema]) -> BioMessageState:
    if runtime.context['persona'] == "agent":
        prompt_str = agent_analyze_and_classify_prompt
        courtesy_prompt = agent_courtesy_query_prompt
        personal_prompt = agent_personal_query_prompt
    else:
        prompt_str = me_analyze_and_classify_prompt
        courtesy_prompt = me_courtesy_query_prompt
        personal_prompt = me_personal_query_prompt

    # print(f"state counter is {state['ctr']}")
    prompt_template = Prompt.from_template(prompt_str)
    chain = prompt_template | model
    question = state["messages"][-1].content
    response = chain.invoke({"loggedin_name": runtime.context['loggedin_name'],
                             "name": runtime.context['name'], "question": question})
    ctr = state['ctr']
    personal_ctr = state['personal_ctr']
    courtesy_ctr = state['courtesy_ctr']
    logger.info(f"type of question is : {response.content.lower()}")
    if response.content.lower() == "professional":
        if ctr >= runtime.context['ctr_th']:
            main_resp = {"role": "ai", "content": "Hope you got enough information!. Have to go. Good Bye!"}
        else:
            main_resp = query_or_respond(state, runtime)
        ctr = 1
    elif response.content.lower() == "courtesy":
        if courtesy_ctr >= runtime.context['courtesy_ctr_th']:
            main_resp = {"role": "ai", "content": "Nice talking to you!. Have to go. Good Bye!"}
        else:
            main_resp = courtesy_query(state, courtesy_prompt, runtime.context['name'],
                                       runtime.context['loggedin_name'])
        courtesy_ctr = 1
    else:
        if personal_ctr >= runtime.context['personal_ctr_th']:
            main_resp = {"role": "ai", "content": "Too many personal questions - Good Bye!"}
        else:
            main_resp = personal_query(state, personal_prompt, runtime.context['name'],
                                       runtime.context['loggedin_name'])
        personal_ctr = 1
    return {"messages": [main_resp], "ctr": ctr, "personal_ctr": personal_ctr, "courtesy_ctr": courtesy_ctr}


def courtesy_query(state: MessagesState, courtesy_prompt, name, loggedin_name):
    system_message_content = courtesy_prompt.format(name=name, loggedin_name = loggedin_name)

    prompt = [SystemMessage(system_message_content)] + state["messages"]

    response = model.invoke(prompt)
    return response


def personal_query(state: MessagesState, personal_prompt, name, loggedin_name):
    system_message_content = personal_prompt.format(name=name)
    prompt = [SystemMessage(system_message_content)] + state["messages"]

    response = model.invoke(prompt)
    return response


# Step 3: Generate a response using the retrieved content.
def generate(state: BioMessageState, runtime: Runtime[ContextSchema]) -> MessagesState:
    """Generate answer."""
    # print("inside generate")
    # Get generated ToolMessages
    recent_tool_messages = []
    for message in reversed(state["messages"]):
        if message.type == "tool":
            recent_tool_messages.append(message)
        else:
            break
    tool_messages = recent_tool_messages[::-1]

    # Format into prompt
    docs_content = "\n\n".join(doc.content for doc in tool_messages)

    if runtime.context['persona'] == "agent":
        generate_prompt = agent_generate_message_prompt.format(name=runtime.context['name'],
                                                               loggedin_name=runtime.context['loggedin_name'])
    else:
        generate_prompt = me_generate_message_prompt.format(name=runtime.context['name'],
                                                            loggedin_name=runtime.context['loggedin_name'])

    system_message_content = generate_prompt + f"{docs_content}"

    conversation_messages = [
        message
        for message in state["messages"]
        if (message.type in ("human", "system") or (message.type == "ai" and not message.tool_calls))
    ]
    prompt = [SystemMessage(system_message_content)] + conversation_messages
    # print(f"prompt is ${prompt}")

    # Run
    response = model.invoke(prompt)
    return {"messages": [response]}

# def stop_condition(state: BioMessageState):
#     msg = state["messages"][-1]
#     # print(f"in stop condition, msg type is {msg.type} and msg content is {msg.content}")
#     if msg.type == "human" and msg.content.startswith("bye"):
#         print("Exceeding your quota or personal/courtesy exceeded limits - exiting")
#         return True
#     else:
#         return False
#
#
# def spacer_node(state: BioMessageState) -> MessagesState:
#     # print("In spacer node")
#     resp_msg = state["messages"][-1]
#     # print(resp_msg.content)
#     input_message = input("Mohamed: ")
#     return {"messages": [HumanMessage(input_message)]}
#     # return state

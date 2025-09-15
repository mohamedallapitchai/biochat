import logging
import operator
from dataclasses import dataclass
from typing import TypedDict, Annotated

from langchain_core.messages import SystemMessage, AIMessage
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnablePassthrough
from langchain_core.tools import tool
from langgraph.graph import MessagesState
from langgraph.runtime import Runtime

from model.model import model, guard_rails
from persona.agent import agent_analyze_and_classify_prompt, agent_courtesy_query_prompt, agent_personal_query_prompt, \
    agent_generate_message_prompt
from persona.me import me_analyze_and_classify_prompt, me_courtesy_query_prompt, me_personal_query_prompt, \
    me_generate_message_prompt
from stores.store import doc_retriever
from stores.user_data import user_df
import pandas as pd

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


def replace_braces(metadata):
    for key, value in metadata.items():
        if type(value) is str:
            metadata[key] = value.replace("{", "{{").replace("}", "}}")
    return metadata


@tool(response_format="content_and_artifact")
def retrieve(query: str):
    """Retrieve information related to a query asking for professional information"""
    # print("INSIDE TOOL")

    # retrieved_docs = vector_store.similarity_search(query, k=2)
    retrieved_docs = doc_retriever.invoke(query)
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
    logger.info(f"response content in query_or_respond is {response}")
    return response
    # return {"messages": [response]}


def retrieve_user_info(name):
    """Retrieve information related to a query like 'do you know me' or 'tell me about me' or
    'what do you know about me"""
    name_splits = name.split(" ")
    (first_name, last_name) = name_splits[0], " ".join(name_splits[1:])
    logger.info(f"first name is {first_name}, last name is {last_name}")

    try:
        df = user_df[(user_df["Last Name"] == last_name) & (user_df["First Name"] == first_name)]

        if df.empty:
            return "", "", ""
        else:
            company = df['Company'].iloc[0] if not pd.isna(df['Company'].iloc[0]) else ""
            logger.info(f"Company is {company}")
            position = df['Position'].iloc[0] if not pd.isna(df['Position'].iloc[0]) else ""
            logger.info(f"Position is {position}")
            values = df['Values'].iloc[0] if not pd.isna(df['Company'].iloc[0]) else ""
            logger.info(f"Values is {values}")
            return company, position, values
    except Exception as e:
        logger.error(f"Caught an exception: {e}")
        return "", "", ""


def analyze_and_classify(state: BioMessageState, runtime: Runtime[ContextSchema]) -> BioMessageState:
    if runtime.context['persona'] == "agent":
        prompt_str = agent_analyze_and_classify_prompt
        courtesy_prompt = agent_courtesy_query_prompt
        personal_prompt = agent_personal_query_prompt
    else:
        prompt_str = me_analyze_and_classify_prompt
        courtesy_prompt = me_courtesy_query_prompt
        personal_prompt = me_personal_query_prompt

    question = state["messages"][-1].content
    prompt_template = ChatPromptTemplate.from_messages(("system", prompt_str))
    guard_chain = prompt_template | (guard_rails | model) | StrOutputParser()

    response = guard_chain.invoke({"loggedin_name": runtime.context['loggedin_name'],
                                   "name": runtime.context['name'], "question": question})
    ctr = 0
    personal_ctr = 0
    courtesy_ctr = 0
    logger.info(f"type of question is : {response.lower()}")
    if response.lower() == "professional":
        if ctr >= runtime.context['ctr_th']:
            main_resp = {"role": "ai", "content": "Hope you got enough information!. Have to go. Good Bye!"}
        else:
            main_resp = query_or_respond(state, runtime)
        ctr = 1
    elif response.lower() == "courtesy":
        if courtesy_ctr >= runtime.context['courtesy_ctr_th']:
            main_resp = {"role": "ai", "content": "Nice talking to you!. Have to go. Good Bye!"}
        else:
            main_resp = courtesy_query(state, courtesy_prompt, runtime.context['name'],
                                       runtime.context['loggedin_name'])
        courtesy_ctr = 1
    elif response.lower() == "personal":
        if personal_ctr >= runtime.context['personal_ctr_th']:
            main_resp = {"role": "ai", "content": "Too many personal questions - Good Bye!"}
        else:
            main_resp = personal_query(state, personal_prompt, runtime.context['name'],
                                       runtime.context['loggedin_name'])
        personal_ctr = 1
    else:
        main_resp = AIMessage(response)

    return {"messages": [main_resp], "ctr": ctr, "personal_ctr": personal_ctr, "courtesy_ctr": courtesy_ctr}


def courtesy_query(state: MessagesState, courtesy_prompt, name, loggedin_name):
    #    system_message_content = courtesy_prompt.format(name=name, loggedin_name=loggedin_name)

    (company, position, comment) = retrieve_user_info(loggedin_name)
    prompt = ChatPromptTemplate.from_messages([
        ("system", courtesy_prompt),
        *state["messages"]
    ])

    guard_chain = prompt | (guard_rails | model)
    response = guard_chain.invoke({"name": name, "company_name": company,
                                   "profession": position, "loggedin_name": loggedin_name,
                                   "comment": comment})

    logger.info(f"type of response is: {type(response)}")
    return response


def personal_query(state: MessagesState, personal_prompt, name, loggedin_name):
    system_message_content = personal_prompt.format(name=name, loggedin_name=loggedin_name)
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
    docs_content = "\n\n".join(doc.content.replace("{", "{{").replace("}", "}}") for doc in tool_messages)
    # docs_content = "\n\n".join(doc.content[''] for doc in tool_messages)

    if runtime.context['persona'] == "agent":
        generate_prompt = agent_generate_message_prompt
    else:
        generate_prompt = me_generate_message_prompt

    system_message_content = generate_prompt + f"{docs_content}"

    conversation_messages = [
        message
        for message in state["messages"]
        if (message.type in ("human", "system") or (message.type == "ai" and not message.tool_calls))
    ]
    # prompt = [SystemMessage(system_message_content)] + conversation_messages
    # print(f"prompt is ${prompt}")

    # Run
    # response = model.invoke(prompt)
    prompt = ChatPromptTemplate.from_messages([
        ("system", system_message_content),
        *conversation_messages
    ])
    guard_chain = prompt | (guard_rails | model)
    response = guard_chain.invoke({"name": runtime.context['name'], "loggedin_name": runtime.context['loggedin_name']})
    logger.info(f"response is {response}")
    return {"messages": [response]}

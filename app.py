import requests
from flask import Flask, request, jsonify # type: ignore
from llmproxy import generate, retrieve, text_upload
from bs4 import BeautifulSoup
import json
import os
import re

GOOGLE_API_KEY = os.environ.get("googleApiKey")
SEARCH_ENGINE_ID = os.environ.get("searchEngineId")
ROCKETCHAT_URL = "https://chat.genaiconnect.net/api/v1/chat.postMessage"
RC_token = os.environ.get("RC_token")
RC_userId = os.environ.get("RC_userId")

app = Flask(__name__)

awaiting_response = {} # Store user states, e.g., awaiting for more information

@app.route('/', methods=['POST'])
def hello_world():
   return {"text":'Hello from Koyeb - you reached the main page!'}

@app.route('/query', methods=['POST'])
def main():
    data = request.get_json() 

    # Extract relevant information
    user = data.get("user_name", "Unknown")
    user_query = data.get("text", "")

    print(data)

    # Ignore bot messages
    if data.get("bot") or not user_query:
        return {"status": "ignored"}
    
    # UPLOAD useful rag contexts 

    # MAIN FUNCTIONALITY OF THE BOT
    # First retrieve the information from the rag_context (if any)
    rag_context = retrieve(
        query=user_query,
            session_id='miniproject_rag_5',
            rag_threshold= 0.5,
            rag_k=2
    )

    # Combine query with rag
    query = f"{user_query}\nCurrent rag_context (not web): {rag_context_string_simple(rag_context)}"

    response = ""
    while True:
        response = AI_Agent(query)

        tool = extract_tool(response)
        if tool:
            query = eval(tool)
            if tool.startswith("get"):
                # Query an LLM to check whether or not this new context should be added to the rag_context
                decision, summary = should_store_in_rag(user_query, query)
                if decision:
                    response = text_upload(
                        text = json.dumps(summary),
                        session_id = 'miniproject_rag_5',
                        strategy = 'fixed')
        else:
            break
    
    
    return {"text": response}

@app.errorhandler(404)
def page_not_found(e):
    return "Not Found", 404

def AI_Agent(query):
    system= f"""
            You are an AI agent designed to advise Tufts University computer
            science students. In addition to your own intelligence, you are
            given access to some tools to access the web.

            Given a query from the user, and some context, your job will be to
            determine whether you have enough information in the context to 
            provide the user with an accurate and complete answer. If you are
            not able to provide an accurate answer, strictly only respond with
            the tool's name and parameters that you want to execute to get more
            information.

            The ouput of tool execution will be shared with you so you can decide
            your next steps. If the user provides you with some urls and summaries. 
            Choose the most appropriate url to use the get_page tool described
            below, so that you can retrieve information from there.
            If the user provides you with more information from the web, simply
            answer the student's original query.
            If you are still not able to answer the student's 
            question accurately, tell him/her you are unable to do so and
            suggest to get in touch with his/her advisor.

            ### PROVIDED TOOLS INFORMATION ###
            ## 1. Tool to retrieve a list of urls from the web along with a 
            brief summary about them.
            ## Intructions: Remember that you have a query from the user, make
            sure that the parameter you pass to this tool is an enhanced query,
            suitable for a google search.

            Name: web_search
            Parameters: query
            example usage: web_search("Tufts CS Major requirements")

            ## 2. Tool to actually retrieve information from a given url.
            
            Name: get_page
            Parameters: url
            example usage: get_page("https://www.eecs.tufts.edu/~fahad/")
            """

    response = generate(
        model='4o-mini',
        system=system,
        query=query,
        temperature=0.1,
        lastk=3,
        session_id="miniproject_0",
        rag_usage=False
    )
    return response['response']

def extract_tool(text):
    match = re.search(r'web_search\([^)]*\)', text)
    if match:
        return match.group()
    
    match = re.search(r'get_page\([^)]*\)', text)
    if match:
        return match.group()
    return ""

# function to create a context string from retrieve's return val
def rag_context_string_simple(rag_context):

    context_string = ""

    i=1
    for collection in rag_context:
    
        if not context_string:
            context_string = """The following is additional context that may be helpful in answering the user's query."""

        context_string += """
        #{} {}
        """.format(i, collection['doc_summary'])
        j=1
        for chunk in collection['chunks']:
            context_string+= """
            #{}.{} {}
            """.format(i,j, chunk)
            j+=1
        i+=1
    return context_string

def format_results_for_llm(results):
    """Format a list of dictionaries into a string for LLM input"""
    formatted_results = "\n\n".join(
        [f"Link: {item['link']}\nSummary: {item['summary']}" for item in results]
    )
    return formatted_results

def web_search(query, num_results=5):
    """Perform a Google search and return the top result links with summaries"""

    url = "https://www.googleapis.com/customsearch/v1"
    params = {
        "key": GOOGLE_API_KEY,
        "cx": SEARCH_ENGINE_ID,
        "q": query,
        "num": num_results
    }
    
    try:
        response = requests.get(url, params=params)
        response.raise_for_status()
        data = response.json()

        # Extract URLs and summaries (snippets) from search result items
        results = [
            {"link": item["link"], "summary": item.get("snippet", "No summary available")}
            for item in data.get("items", [])
        ]

        return format_results_for_llm(results)  # Return a list of dictionaries

    except requests.exceptions.RequestException as e:
        return f"Error: {e}"

def scrape_all_text(url):
    response = requests.get(url)
    soup = BeautifulSoup(response.content, 'html.parser')

    # List of tags you want to include
    tags_to_include = ['p', 'h1', 'h2', 'h3', 'h4', 'ol', 'ul', 'li', 'a', 
                       'strong', 'em', 'table', 'tbody', 'tr', 'td']

    content = []
    for tag in tags_to_include:
        elements = soup.find_all(tag)
        for element in elements:
            # Append the cleaned text from each tag to the content list
            content.append(element.get_text(strip=True))

    return '\n'.join(content)


def should_store_in_rag(query, web_content):
        """
        Asks the LLM whether the web data should be stored in RAG.
        Returns a tuple (decision, summary)
        """
        system_prompt = """
        You are a knowledge base for a Tufts CS advising chatbot. Given the user 
        question and retrieved web search results, determine:
        - Should this information be stored in the chatbot's internal knowledge base (RAG)
        - If yer, provide a concise, structured summary suitable for storage.
        Note that it might be better if time-sensitive or dynamic information is not
        stored in RAG as this might change. However, evergreen and useful information
        should be stored in RAG.

        The output format shuld be:
        - Decision: [STORE // DISCARD]
        - Summary: [Concise summary]
        """

        response = generate(
            model = '4o-mini',
            system = json.dumps(system_prompt),
            query = f'Query: {json.dumps(query)}. Web content: \n{web_content}',
            temperature=0.0,
            lastk=5,
            session_id='miniproject_0')
        # print(f"\n\n{response}\n\n")
        decision = "STORE" in response['response']
        summary = None
        if decision:
            summary_start = response['response'].find("- Summary:")
            if summary_start != -1:
                summary = response['response'][summary_start + len("- Summary:"):]
        return decision, summary

def get_page(url):
    response = requests.get(url)
    soup = BeautifulSoup(response.content, 'html.parser')

    # List of tags you want to include
    tags_to_include = ['p', 'h1', 'h2', 'h3', 'h4', 'ol', 'ul', 'li', 'a', 
                       'strong', 'em', 'table', 'tbody', 'tr', 'td']

    content = []
    for tag in tags_to_include:
        elements = soup.find_all(tag)
        for element in elements:
            # Append the cleaned text from each tag to the content list
            content.append(element.get_text(strip=True))

    return '\n'.join(content)

def send_message_to_rocketchat(channel, text):
    headers = {
        "X-Auth-Token": RC_token,
        "X-User-Id": RC_userId,
        "Content-Type": "application/json"
    }
    payload = {
        "channel": channel,  # Use the channel ID or room name
        "text": text
    }
    
    response = requests.post(ROCKETCHAT_URL, json=payload, headers=headers)
    
    if response.status_code == 200:
        print("Message sent successfully!")
    else:
        print(f"Failed to send message: {response.status_code}, {response.text}")

if __name__ == "__main__":
    app.run()
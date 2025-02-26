import requests
from flask import Flask, request, jsonify # type: ignore
from llmproxy import generate
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
    message = data.get("text", "")

    print(data)

    # Ignore bot messages
    if data.get("bot") or not message:
        return {"status": "ignored"}

    # MAIN FUNCTIONALITY OF THE BOT
    
    response = AI_agent(user, message)
    
    return {"text": response}
    
@app.errorhandler(404)
def page_not_found(e):
    return "Not Found", 404

def AI_agent(user, user_message):
    if user not in awaiting_response:
        system= f"""
                You are an AI agent designed to handle queries from international
                students at Tufts University. Specifically, you can support students
                with the following:
                    - Immigration and Visa Assistance: Guidance on obtaining and 
                    maintaining valid U.S. immigration status.
                    - Orientation Programs: Initiatives designed to ease your
                    transition to Tufts and the surrounding community.
                    - Information about Cultural and Educational Events
                    - Practical Support: Assistance with everyday matters such as
                    housing, navigating U.S. systems, and accessing campus resources.
                
                You will be given a lot of context from Tuft's international
                center website. Make sure that your answers are based on this 
                context and with some of your own intelligency too!
                Take into account that the user's username is {user}. This is 
                formated by [name].[lastname]. Use this information if applicable!

                Break down the user's query as follows:

                - First, determine if the student is asking a specific query concerning
                the international center. If not, then still reply to the user but
                at the end emphasize what you can help with.

                - Second, determine if you strictly need more information from
                the user to be able to answer the user's query accurately. If the
                answer to a query will vary A LOT depending on the user's situation.
                Then ask him a question about it. Note that this should be done
                only if you strictly need extra information, not for every query.
                If you decide to ask questions to the user end your response with
                the token $$QUESTION$$.

                For example: you may need to know the user's last name and in which
                program he/she is to help him/her find his/her advisor.
                """
        
        # First enhance query for google_search
        enhanced_query = enhance_query(user_message)

        # Get context from the web
        contexts = google_search(enhanced_query.strip('"'))

        # Pass context to LLM:
        response = generate(
            model= '4o-mini',
            system=system,
            query=f"""
                  Interact with the user/answer his query :{user_message}. Here
                  is the context available for use: {contexts}. If the answer
                  is not available in the context make sure to reply with your
                  own intelligence.
                  """,
            temperature=0.1,
            lastk=3,
            session_id=f'BOT-EDU_{user}'
        )
        new_response, token = extract_question(response['response'])
        if token == "$$QUESTION$$":
            awaiting_response[user] = [user_message, contexts]
        return new_response
    # If chatbot is awaiting response from the user
    old_user_message, contexts = awaiting_response[user]

    system= """
            You are a chatbot that aids another chatbot with advising international
            students at Tufts University. You will be given a query previously
            made by a user, plus additional information the user gave related to
            this question, plust additional context from the web. Using this,
            you should be able to provide with a more robust response to the user.

            If no useful information is provided in contexts and the additional
            information from the user, then use your own intelligence to answer
            the query.
            """
    response = generate(
        model='4o-mini',
        system=system,
        query=f'The original query you must answer: {old_user_message}. The information from
                the web: {contexts}. The additional info from the user: {user_message}',
        temperature=0.1,
        lastk=5,
        session_id=f'BOT-EDU_{user}'
    )
    # Remove from awaiting_response
    del awaiting_response[user]
    return response['response']
    

def extract_question(text):
    match = re.search(r'\$\$QUESTION\$\$$', text)
    if match and text.endswith("$$QUESTION$$"):
        question = match.group()
        text = text[:match.start()].rstrip()
        return text, question
    return text, None    

def answer_query(user, user_message):
    # Enhance students query
    enhanced_query = enhance_query(user_message)

    # use the enhanced query to query the Google API
    contexts = google_search(enhanced_query.strip('"'))

    if not contexts:
        response = generate(
            model = '4o-mini',
            system = f"""
                    You are an AI agent designed to handle queries from international
                    students at Tufts University. Specifically, you can support students
                    with the following:
                        - Immigration and Visa Assistance: Guidance on obtaining and 
                        maintaining valid U.S. immigration status.
                        - Orientation Programs: Initiatives designed to ease your
                        transition to Tufts and the surrounding community.
                        - Information about Cultural and Educational Events
                        - Practical Support: Assistance with everyday matters such as
                        housing, navigating U.S. systems, and accessing campus resources.
                    
                    Reply to the user's query, but make sure to emphasize at the
                    end what you can help with specifically.
                    """,
            query=user_message,
            temperature=0.1,
            lastk=3,
            session_id=f'BOT-Eduardo_{user}'
        )
        return response
    
    # If useful context found, use it to generate an answer
    response = generate(
        model = '4o-mini',
        system= """
                You are an advising chatbot for international Tufts students. You
                will be provided with a lot of context from the web and a query
                from the student. You should answer as accurately as possible.
                Prioritize concise answers over long and confusing ones. Make
                sure that your answer is based on the context provided.

                If you feel that you would need additional information to answer
                the question more accurately, provide some questions that could
                be asked to the user to deliver a more tailored answer. Format
                you response as follows: [your response] and at the end
                $$Question1 Question2 Question3 ...$$
                """,
        query= f"Answer the query by a student: {user_message} basing your answer \
                with the following information: {contexts}",
        temperature=0.0,
        lastk=5,
        session_id=f'BOT-Eduardo_{user}'
    )
    return response

def google_search(query, num_results=2):
    """Perform a Google search and return the top results"""

    url = "https://www.googleapis.com/customsearch/v1"
    # print(f"The query is: {query}")
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
        contexts = []

        # Iterate over search result items
        for item in data.get("items", []):
            # Extract URL from the item
            url = item["link"]
            # print(url)
            
            # Scrape the webpage content
            page_content = scrape_all_text(url)
            contexts.append(page_content)

        return '\n'.join(contexts)

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

def enhance_query(query):
    """
    This method uses GenAI to get the query from the user and turn it into 
    a suitable form for a google search.  
    """
    response = generate(
        model = '4o-mini',
        system= """
                You are assiting a chatbot that advises Tufts international
                students. Given a question from a student, generate a concise
                and effective Google search query to retrieve the best
                information from the web. Respond **only** with the query—no
                extra text. Keep it short and relevant!
                """,
        query = query,
        temperature=0.0,
        lastk=5,
        session_id='GenericSession',
        rag_usage=False)
    
    return response['response']

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
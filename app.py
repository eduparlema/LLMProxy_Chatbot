import requests
from flask import Flask, request, jsonify # type: ignore
from llmproxy import generate
from bs4 import BeautifulSoup
import json
import os

GOOGLE_API_KEY = os.environ.get("googleApiKey")
SEARCH_ENGINE_ID = os.environ.get("searchEngineId")
ROCKETCHAT_URL = "https://chat.genaiconnect.net/api/v1/chat.postMessage"
RC_token = os.environ.get("RC_token")
RC_userId = os.environ.get("RC_userId")

app = Flask(__name__)

conversation_state = {} # Store user states, e.g., awaiting for more information

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
    
    # response = answer_query(message)

    if user in conversation_state and conversation_state[user] == "awaiting_details":
        # Process user's additional information
        del conversation_state[user]
        response = ""
        return {"text": response}
    # If not in a multi-step conversation, ask for more details first 
    
    return {"text": response}
    
@app.errorhandler(404)
def page_not_found(e):
    return "Not Found", 404

def answer_query(user, user_message):
    # Enhance students query
    enhanced_query = enhance_query(user_message)

    # use the enhanced query to query the Google API
    contexts = google_search(enhanced_query.strip('"'))

    if not contexts:
        response = generate(
            model = '4o-mini',
            system = """
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
                    
                    Take into account that the user's username is {user}. This is 
                    formated by [name].[lastname]. Use this information if applicable!
                    Reply to the user's query, but make sure to emphasize at the
                    end what you can help with specifically.
                    """,
            query=user_message,
            temperature=0.1,
            lastk=3,
            session_id=f'BOT-Eduardo_{user}-no-context'
        )
        return {"text": response['response']}
    
    # If useful context found, use it to generate an answer
    response = generate(
        model = '4o-mini',
        system= """
                You are an advising chatbot for international Tufts students. You
                will be provided with a lot of context from the web and a query
                from the student. You should answer as accurately as possible.
                Prioritize concise answers over long and confusing ones. Make
                sure that your answer is based on the context provided.

                Also, determine if the user's query should be scalated to his/her
                advisor at the international center. If so, at the end of your
                response include the token $$particular$$. Do NOT add in your
                response anything related to: If you have a particular question,
                get in touch with your advisor or I recommend getting in touch
                with your advisor. This will be taken care of with another tool
                if you just add the token above.
                """,
        query= f"Answer the query by a student: {user_message} basing your answer \
                with the following information: {contexts}",
        temperature=0.0,
        lastk=5,
        session_id=f'BOT-Eduardo_{user}-context'
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
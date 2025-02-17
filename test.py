import requests

response_main = requests.get("https://clear-gerri-eduardo-tufts-4ace34f0.koyeb.app/")
print('Web Application Response:\n', response_main.text, '\n\n')


data = {"text":"tell me about tufts"}
response_llmproxy = requests.post("https://clear-gerri-eduardo-tufts-4ace34f0.koyeb.app/query", json=data)
print('LLMProxy Response:\n', response_llmproxy.text)
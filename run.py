import os
import requests
def send_simple_message():
  	return requests.post(
  		"https://api.mailgun.net/v3/sandbox1cc50a139c9c456eb7703914fbf8b07e.mailgun.org/messages",
  		auth=("api", os.getenv('API_KEY', 'API_KEY')),
  		data={"from": "Mailgun Sandbox <postmaster@sandbox1cc50a139c9c456eb7703914fbf8b07e.mailgun.org>",
			"to": "HOPEFREY MOTARI <hopefreymosingi1@gmail.com>",
  			"subject": "Hello HOPEFREY MOTARI",
  			"text": "Congratulations HOPEFREY MOTARI, you just sent an email with Mailgun! You are truly awesome!"})
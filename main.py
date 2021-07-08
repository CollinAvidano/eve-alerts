from dateutil.parser import parse
from discord import Webhook, AsyncWebhookAdapter
from email.message import EmailMessage
from smtplibaio import SMTP, SMTP_SSL

import os
import aiohttp
import asyncio
import configparser
import datetime
import discord
import json
import logging
import pandas as pd
import pytz
import ssl
import websockets


def log_debug(string):
    logging.debug(string)
    print(string)

def log_info(string):
    logging.info(string)
    print(string)

def log_error(string):
    logging.error(string)
    print(string)

async def send_emails(sender, recipients, subject, content, server, port, password):
    # Build the EmailMessage object
    message = EmailMessage()
    message.add_header("From", str(sender))
    message.add_header("To", str(recipients))
    message.add_header("Subject", subject)
    message.add_header("Content-type", "text/plain", charset="utf-8")
    message.set_content(content)

    # Send the e-mail:
    context = ssl.create_default_context()
    async with SMTP_SSL(hostname=server, port=port, context=context) as client:
        await client.ehlo()
        await client.auth(sender, password)
        await client.sendmail(sender, recipients, message.as_string())

async def send_discord(notification, webhook_url, username):
    async with aiohttp.ClientSession() as session:
        webhook = Webhook.from_url(webhook_url, adapter=AsyncWebhookAdapter(session))
        await webhook.send(notfication, username=username)

class alert_module:

    def __init__(self):
        pass

    async def check(self, json_message):
        print(json_message)

class rare_ship_hunter_module(alert_module):

    def __init__(self):
        self.config = configparser.ConfigParser()
        self.config.read('ship_hunter.ini')
        self.recipients = self.config['mail']['recipients'].split(',')

        self.system_df = pd.DataFrame(pd.read_csv(r'sdes/mapSolarSystems.csv'), columns= ['solarSystemID','solarSystemName'])
        self.ship_df = pd.DataFrame(pd.read_csv(r'sdes/limited-issue.csv'), columns= ['typeID','typeName'])

    async def check(self, json_message):
        if 'attackers' in json_message:
            for attacker in json_message['attackers']:
                if 'ship_type_id' in attacker:
                    if (self.ship_df['typeID'] == int(attacker['ship_type_id'])).any():
                        ship_id = int(attacker['ship_type_id'])
                        solar_system_id = int(json_message['solar_system_id'])
                        character_id = str(attacker['character_id'])

                        system_name = self.system_df[self.system_df['solarSystemID'] == solar_system_id].iloc[0, 1]
                        ship_name = self.ship_df[self.ship_df['typeID'] == ship_id].iloc[0, 1]
                        notfication_message = "Spotted " + ship_name + " in system " + system_name
        
                        subject = notfication_message
                        content = notfication_message + "\n https://evewho.com/character/" + character_id
                        log_info(notfication_message)
                        log_debug("Sending notifications for matching ship")

                        await send_emails(self.config['mail']['sender-email'], self.recipients, subject, content, self.config['mail']['server'], self.config['mail']['port'], self.config['mail']['sender-password'])
                        await send_discord(content, self.config['discord']['webhook-url'], self.config['discord']['username'])

                        return



class character_hunter_module(alert_module):

    def __init__(self):
        self.config = configparser.ConfigParser()
        self.config.read('character_hunter.ini')
        self.recipients = self.config['mail']['recipients'].split(',')

        self.system_df = pd.DataFrame(pd.read_csv(r'sdes/mapSolarSystems.csv'), columns= ['solarSystemID','solarSystemName'])
        self.character_df = pd.DataFrame(pd.read_csv(r'sdes/characters.csv'), columns= ['typeID','typeName'])

    async def check(self, json_message):
        if 'attackers' in json_message:
            for attacker in json_message['attackers']:
                if 'character_id' in attacker:
                    if (self.character_df['characterID'] == int(attacker['character_id'])).any():
                        system_name = self.system_df[self.system_df['solarSystemID'] == solar_system_id].iloc[0, 1]
                        character_name = self.character_df[self.character_df['characterID'] == character_id].iloc[0, 1]
                        notfication_message = "Spotted " + character_name + " in system " + system_name
                        
                        log_debug("Sending email notifications for matching character")
                        log_info(notfication_message)

                        # E-mail subject and content:
                        subject = notfication_message
                        content = notfication_message + \
                        "\n Ship type: https://zkillboard.com/ship/" + ship_id + \
                        "\n https://evewho.com/character/" + character_id

                        await send_emails(self.config['mail']['sender-email'], self.recipients, subject, content, self.config['mail']['server'], self.config['mail']['port'], self.config['mail']['sender-password'])
                        await send_discord(content, self.config['discord']['webhook-url'], self.config['discord']['username'])

class alert_server:
 
    def __init__(self):
        os.makedirs("./logs", exist_ok=True)

        logger = logging.getLogger('discord')
        logger.setLevel(logging.DEBUG)
        handler = logging.FileHandler(filename='./logs/discord.log', encoding='utf-8', mode='w')
        handler.setFormatter(logging.Formatter('%(asctime)s:%(levelname)s:%(name)s: %(message)s'))
        logger.addHandler(handler)

        logger = logging.getLogger('websockets')
        logger.setLevel(logging.DEBUG)
        handler = logging.FileHandler(filename='./logs/websockets.log', encoding='utf-8', mode='w')
        handler.setFormatter(logging.Formatter('%(asctime)s:%(levelname)s:%(name)s: %(message)s'))
        logger.addHandler(handler)

        logger = logging.getLogger("asyncio")
        handler = logging.FileHandler(filename='./logs/asyncio.log', encoding='utf-8', mode='w')
        handler.setFormatter(logging.Formatter('%(asctime)s:%(levelname)s:%(name)s: %(message)s'))
        logger.addHandler(handler)

        logging.basicConfig(level=logging.DEBUG,
                    format='%(asctime)s %(name)-12s %(levelname)-8s %(message)s',
                    datefmt='%m-%d %H:%M',
                    filename='./logs/server.log',
                    filemode='w')

        self.alertmodules = [rare_ship_hunter_module(), character_hunter_module()]

        self.time_last_recieved = datetime.datetime.now(pytz.utc)
 
        loop = asyncio.get_event_loop()
        loop.set_debug(True)
        while True:
            loop.run_until_complete(self.socket_handler())


    async def socket_handler(self):
        websocket_url = "wss://zkillboard.com/websocket/"
        message = {
            "action": "sub",
            "channel": "killstream"
        }
        log_debug("Opening Socket")
        try:
            websocket = await asyncio.wait_for(websockets.connect(websocket_url), 10)
            log_debug("Sending Subscription Request")
            await websocket.send(json.dumps(message, indent = 4))

            log_debug("Handling Loop Start")
            async for message in websocket:
                await self.consume_message(message)
                    
        except:
            log_error("Error. Will Try Reconnecting")
            return

    async def consume_message(self, message):
        json_message = json.loads(message)
        self.time_last_recieved = datetime.datetime.now(pytz.utc)
        killmail_time = parse(json_message['killmail_time'])
        log_info('killmail received')
        if self.time_last_recieved-datetime.timedelta(hours=1) < killmail_time:
            for module in alert_modules:
                module.check(killmail)


if __name__ == "__main__":
    responder = alert_server()

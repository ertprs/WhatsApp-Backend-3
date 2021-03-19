from pymongo import MongoClient


class TwilioConfig:
    def __init__(self):
        client = MongoClient("localhost", 27017)
        db = client["whatsapp_twilio_config"]
        self.configs = db.configs

    def get_config(self, appId):
        config = self.configs.find_one({"appId": appId})
        return config

    def update_config(self, appId, is_active, msisdn):
        config = self.configs.update_one({"appId": appId}, {"$set":{"isActive": is_active}})
        return config

    def create_config(self, appId, auth_token, account_sid, msisdn):
        config = self.configs.find_one({"appId": appId})
        if config is not None:
            return config
        config = self.configs.insert_one({
            "appId": appId,
            "isActive": False,
            "msisdn": msisdn,
            "config": {
                "authToken": auth_token,
                "accountSid": account_sid
            }
        })
        return config
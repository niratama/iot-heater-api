#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import responder
import pigpio
from pigpio_dht import DHT11

# アクセス用トークンを環境変数から取得する
# dd if=/dev/urandom bs=1 count=128 | sha256sum
TOKEN = os.getenv("AUTH_TOKEN", default="")

api = responder.API()

# 温度センサーが接続されているGPIOのピン番号
DHT11_PIN = 14
# サーボが接続されているGPIOのピン番号
MIN_SERVO_PIN = 23
MED_SERVO_PIN = 18
# サーボのパルス幅(500-2500)
SERVO_MIN = 1000
SERVO_MAX = 2000

# デバイス処理クラス
class Devices:
    def __init__(self):
        # サーボの初期化
        self.pi = pigpio.pi()
        self.sensor = DHT11(DHT11_PIN, pi=self.pi)
        self.set_power(0);

    def set_power(self, value):
        # MIN/MEDでサーボの取り付け向きが違うのでMINとMAXが入れ替わる
        min_value = SERVO_MAX if value & 1 else SERVO_MIN
        med_value = SERVO_MIN if value & 2 else SERVO_MAX

        self.pi.set_servo_pulsewidth(MIN_SERVO_PIN, min_value)
        self.pi.set_servo_pulsewidth(MED_SERVO_PIN, med_value)

    def get_power(self):
        min_value = self.pi.get_servo_pulsewidth(MIN_SERVO_PIN)
        med_value = self.pi.get_servo_pulsewidth(MED_SERVO_PIN)

        # MIN/MEDでサーボの取り付け向きが違うのでMINとMAXが入れ替わる
        center = (SERVO_MIN + SERVO_MAX) / 2
        value = ((1 if center < min_value else 0) |
                 (2 if med_value < center else 0))

        return value

    def get_env(self):
        try:
            data = self.sensor.read(retries=5)
        except TimeoutError:
            data = {"valid": False}
        return data

dev = Devices()

# HTTPのエラーレスポンスを作成する
def http_error(resp, status_code):
    resp.status_code = status_code
    resp.media = {"success": False}
    return False

# アクセス権限があるかどうかチェックする
def authorize(req, resp):
    if "token" in req.params:
        token = req.params["token"]
    else:
        auth = req.headers.get("Authorization", None)
        if not auth:
            return http_error(resp, api.status_codes.HTTP_401)
        parts = auth.split()
        if len(parts) != 2 or parts[0].lower() != "bearer":
            return http_error(resp, api.status_codes.HTTP_401)
        token = parts[1]
    if TOKEN == "" or token != TOKEN:
        return http_error(resp, api.status_codes.HTTP_401)
    return True

# スイッチ設定・取得
@api.route("/api/switch")
class SwitchResource:
    async def on_post(self, req, resp):
        if not authorize(req, resp):
            return

        data = await req.media()

        if "value" not in data:
            return http_error(resp, api.status_codes.HTTP_400)

        power = data["value"]
        if type(power) is str:
            power = int(power)
        if type(power) is not int or power < 0 or power > 3:
            return http_error(resp, api.status_codes.HTTP_400)
        dev.set_power(power)
        resp.media = {
            "success": True,
        }

    async def on_get(self, req, resp):
        if not authorize(req, resp):
            return
        power = dev.get_power()
        resp.media = {
            "success": True,
            "value": power
        }

# 温湿度取得
@api.route("/api/env")
class EnvResource:
    async def on_get(self, req, resp):
        if not authorize(req, resp):
            return
        data = dev.get_env();
        if data["valid"]:
            resp.media = {
                "success": True,
                "temp": data["temp_c"],
                "humid": data["humidity"],
            }
        else:
            resp.media = {
                "success": False,
            }

if __name__ == '__main__':
    api.run()

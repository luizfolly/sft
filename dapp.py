from os import environ
import requests, json, time
from eth_abi_ext import decode_packed
from eth_abi.abi import encode
#from web3 import Web3

rollup_server = environ["ROLLUP_HTTP_SERVER_URL"]
ERC20_PORTAL_ADDRESS = "0x9C21AEb2093C32DDbC53eEF24B873BDCd1aDa1DB".lower()
STORE_ADDRESS = environ.get("STORE_ADDRESS", "").lower()

TRANSFER_FUNCTION_SELECTOR = bytes.fromhex("a9059cbb")

balances = {}           # balances[user][erc20] = saldo de cada usuário
deposit_requests = []   # lista de pedidos de depósitos
orphan_deposits = []    # depósitos recebidos, sem pedido
#w3 = Web3()

def str2hex(s):
    return "0x" + s.encode().hex()
#    return "0x" + w3.codec.encode().hex()
#    return "0x" + w3.to_hex(s)
#    return Web3.to_hex(s)

def hex2str(h):
    return bytes.fromhex(h[2:]).decode()

def post(endpoint, payload):
    requests.post(f"{rollup_server}/{endpoint}", json=payload)

def balance_check(user, erc20):
    if user not in balances: balances[user] = {}
    if erc20 not in balances[user]: balances[user][erc20] = 0


# -------------------------------------------------------
def deposit_request(payload, sender):
    rec = {
        "request_id": payload.get("request_id"),
        "depositor": sender,
        "erc20": payload["erc20"].lower(),
        "amount": int(payload["amount"]),
        "user": payload["user"].lower(),
        "matched": False,
    }
    deposit_requests.append(rec)
    return "accept"


# -------------------------------------------------- #
def handle_erc20_deposit(data):
    binary = bytes.fromhex(data["payload"][2:])
    success, erc20, depositor, amount = decode_packed(['bool','address','address','uint256'], binary)
    erc20, depositor, amount = erc20.lower(), depositor.lower(), int(amount)

    # Tenta encontrar o pedido do depósito
    for rec in deposit_requests:
        if not rec["matched"] and rec["depositor"] == depositor and rec["erc20"] == erc20 and rec["amount"] == amount:
            user = rec["user"]
            balance_check(user, erc20)
            balances[user][erc20] += amount
            rec["matched"] = True
            return "accept"

    # Se não encontrar, registra como depósito órfão
    orphan_deposits.append({"depositor": depositor, "erc20": erc20, "amount": amount})
    return "accept"


# -------------------------------------------------- #
def handle_withdraw(sender, payload):
    erc20 = payload["erc20"].lower()
    amount = int(payload["amount"])

    balances[sender][erc20] -= amount
    transfer_payload = TRANSFER_FUNCTION_SELECTOR + encode(['address','uint256'], [STORE_ADDRESS, amount])
    voucher = {"destination": erc20, "payload": "0x" + transfer_payload.hex()}
    post("voucher", voucher)
    return "accept"


# -------------------------------------------------- #
def handle_advance(data):
    sender = data["metadata"]["msg_sender"].lower()

    if sender == ERC20_PORTAL_ADDRESS:
        return handle_erc20_deposit(data)

    payload = json.loads(hex2str(data["payload"]))
    if payload["action"] == "register_expected_deposit":
        return register_expected_deposit(payload, sender)
    if payload["action"] == "withdraw":
        return handle_withdraw(sender, payload)

    return "accept"


# -------------------------------------------------- #
def handle_inspect(data):
    payload = json.loads(hex2str(data["payload"])) if "payload" in data else {}
    if "balance" in payload:
        user = payload["balance"].lower()
        post("report", {"payload": str2hex(json.dumps(balances.get(user, {})))})
    elif "all_balances" in payload:
        post("report", {"payload": str2hex(json.dumps(balances))})
    elif "deposit_requests" in payload:
        pending = [rec for rec in deposit_requests if not rec["matched"]]
        post("report", {"payload": str2hex(json.dumps(pending))})
    elif "orphan_deposits" in payload:
        post("report", {"payload": str2hex(json.dumps(orphan_deposits))})
    return "accept"


# -------------------------------------------------- #
handlers = {"advance_state": handle_advance, "inspect_state": handle_inspect}
finish = {"status": "accept"}

while True:
    response = requests.post(rollup_server + "/finish", json=finish)
    if response.status_code == 202:
        time.sleep(1)
        continue
    rollup_request = response.json()
    handler = handlers[rollup_request["request_type"]]
    finish["status"] = handler(rollup_request["data"])



# -------------------------------------------------- #

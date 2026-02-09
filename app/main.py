import asyncio
import logging
import random
import re
import uuid
import json
import os
import sys
from contextlib import asynccontextmanager
from typing import Optional, Dict, Any, List
from fastapi import FastAPI, Query, HTTPException
from fastapi.responses import JSONResponse, FileResponse
from pydantic import BaseModel
from telethon import TelegramClient, events
from telethon.sessions import StringSession
import httpx

# Adiciona o diretório raiz ao path para permitir importações de módulos
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import (
    API_ID, API_HASH, SESSION_STRING, TARGET_BOT_ID, GROUP_ID,
    DEVICE_MODEL, SYSTEM_VERSION, APP_VERSION, BASE_STORAGE_DIR,
    FOLDER_MAP, VALID_TYPES, CPF_BASES, BASE_ALIASES, PROCESSING_KEYWORDS,
    FINAL_INDICATORS, MAINTENANCE_INDICATORS, HUMAN_DELAY_MIN, HUMAN_DELAY_MAX,
    MAX_ATTEMPTS, TIMEOUT_PER_ATTEMPT, FINAL_CONFIRMATION_DELAY
)

# Configuração de logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# Modelos Pydantic para requisições
class ConsultaRequest(BaseModel):
    type: str
    value: str
    base: Optional[str] = None

# Armazenamento de requisições ativas
active_requests: Dict[str, Dict[str, Any]] = {}

# Flag para indicar se Telegram está conectado
telegram_connected = False

def ensure_storage():
    """Garante que os diretórios de armazenamento existam"""
    if not os.path.exists(BASE_STORAGE_DIR):
        os.makedirs(BASE_STORAGE_DIR, exist_ok=True)
    for folder in FOLDER_MAP.values():
        path = os.path.join(BASE_STORAGE_DIR, folder)
        if not os.path.exists(path):
            os.makedirs(path, exist_ok=True)

def get_cached_data(query_type: str, value: str, base: Optional[str] = None) -> Optional[Dict]:
    """Busca dados em cache"""
    folder = FOLDER_MAP.get(query_type, "Outros")
    filename = f"{value}_{base}.json" if base else f"{value}.json"
    filename = re.sub(r'[\\/*?:"<>|]', "", filename)
    file_path = os.path.join(BASE_STORAGE_DIR, folder, filename)
    if os.path.exists(file_path):
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Erro ao ler cache: {e}")
    return None

def save_to_cache(query_type: str, value: str, data: Dict, base: Optional[str] = None):
    """Salva dados em cache"""
    folder = FOLDER_MAP.get(query_type, "Outros")
    filename = f"{value}_{base}.json" if base else f"{value}.json"
    filename = re.sub(r'[\\/*?:"<>|]', "", filename)
    file_path = os.path.join(BASE_STORAGE_DIR, folder, filename)
    try:
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
    except Exception as e:
        logger.warning(f"Erro ao salvar cache: {e}")

async def human_delay(min_s: Optional[float] = None, max_s: Optional[float] = None):
    """Atraso aleatório para simular comportamento humano"""
    min_delay = min_s or HUMAN_DELAY_MIN
    max_delay = max_s or HUMAN_DELAY_MAX
    await asyncio.sleep(random.uniform(min_delay, max_delay))

def is_processing_message(text: str) -> bool:
    """Verifica se é uma mensagem de processamento (não é final)"""
    if not text:
        return False
    return any(keyword in text for keyword in PROCESSING_KEYWORDS)

def is_final_response(text: str) -> bool:
    """Verifica se a mensagem é uma resposta final do bot"""
    if not text:
        return False
    if any(m in text.lower() for m in ["manutenção", "manutencao"]):
        return True
    if len(text) < 30 and not any(ind in text for ind in ["Total de resultados:", "Consulta concluída"]):
        return False
    if is_processing_message(text):
        return False
    has_indicator = any(indicator in text for indicator in FINAL_INDICATORS)
    if has_indicator:
        return True
    if len(text) > 200 and text.count('\n') > 5 and (text.count('°') > 3 or text.count('•') > 3):
        return True
    return False

def is_maintenance_message(text: str) -> bool:
    """Verifica se a mensagem indica manutenção"""
    return any(indicator in text for indicator in MAINTENANCE_INDICATORS)

def match_button_text(button_text: str, target_base: str) -> bool:
    """Verifica se o texto do botão corresponde à base solicitada"""
    button_text = button_text.lower().strip()
    target_base = target_base.lower().strip()
    if target_base in button_text:
        return True
    aliases = BASE_ALIASES.get(target_base, [])
    return any(alias in button_text for alias in aliases)

def parse_to_json(text: str, query_type: str) -> Dict:
    """Parse avançado da resposta do bot para JSON"""
    clean_text = text
    for marker in ["👤 **Usuário:**", "👤 Usuário:", "🤖 **Bot:**", "🤖 Bot:"]:
        if marker in clean_text:
            clean_text = clean_text.split(marker)[0].strip()
    lines = [line.strip() for line in clean_text.split('\n') if line.strip()]
    data = {
        "tipo_consulta": query_type,
        "total_resultados": None,
        "resultados": [],
        "parsed": {},
        "sections": {},
        "telegraph_link": None,
        "raw_text": clean_text
    }
    for i, line in enumerate(lines):
        if "Total de resultados:" in line:
            try:
                data["total_resultados"] = int(line.split(":")[1].strip())
            except: pass
        if "Abrir relatório completo no Telegraph" in line and i + 1 < len(lines):
            potential_link = lines[i+1].strip()
            if potential_link.startswith(("http", "t.me")):
                data["telegraph_link"] = potential_link
    if not data["telegraph_link"]:
        markdown_pattern = r'\[([^\]]+)\]\((https?://(?:telegra\.ph|telegraph\.co)[^\)]+)\)'
        for line in lines:
            match = re.search(markdown_pattern, line, re.IGNORECASE)
            if match:
                data["telegraph_link"] = match.group(2)
                break
        if not data["telegraph_link"]:
            telegraph_pattern = r'(https?://(?:telegra\.ph|telegraph\.co)[^\s\)]+)'
            for line in lines:
                match = re.search(telegraph_pattern, line, re.IGNORECASE)
                if match:
                    data["telegraph_link"] = match.group(1)
                    break
    resultados = []
    current_result = None
    if "RESULTADO" in clean_text:
        for line in lines:
            if line.startswith("RESULTADO"):
                if current_result: resultados.append(current_result)
                current_result = {"dados": {}, "sections": {}}
                continue
            if current_result is not None:
                if line.startswith("•") and ":" in line:
                    parts = line[1:].split(":", 1)
                    if len(parts) == 2:
                        key, val = [p.strip() for p in parts]
                        current_result["dados"][key] = val
        if current_result: resultados.append(current_result)
    if not resultados:
        current_section = "geral"
        data["sections"][current_section] = {}
        for i, line in enumerate(lines):
            if line.startswith("°") and line.endswith(":") and ":" not in line[1:-1]:
                current_section = line[1:-1].strip().lower()
                data["sections"][current_section] = {}
                continue
            if line.startswith("°") and line[1:].strip().isupper() and ":" not in line:
                current_section = line[1:].strip().lower()
                data["sections"][current_section] = {}
                continue
            marker = None
            if line.startswith("°"): marker = "°"
            elif line.startswith("•"): marker = "•"
            if marker and ":" in line:
                parts = line[1:].split(":", 1)
                if len(parts) == 2:
                    key, val = [p.strip() for p in parts]
                    data["sections"][current_section][key] = val
                    data["parsed"][key] = val
    if resultados:
        data["resultados"] = [r["dados"] for r in resultados]
        data["total_resultados"] = len(resultados)
        data["parsed"] = resultados[0]["dados"]
    return data

async def process_consulta(type: str, value: str, base: Optional[str] = None):
    """Processa uma consulta verificando cache antes de enviar ao bot"""
    global telegram_connected
    if not value:
        raise HTTPException(status_code=400, detail="Valor não fornecido")
    if type not in VALID_TYPES:
        raise HTTPException(status_code=400, detail=f"Tipo inválido. Use: {', '.join(VALID_TYPES)}")
    cached = get_cached_data(type, value, base)
    if cached:
        logger.info(f"✅ Cache hit para {type}: {value}")
        return JSONResponse(content={"status": "success", "source": "cache", **cached})
    if not telegram_connected:
        raise HTTPException(status_code=503, detail="Dados não encontrados em cache e o Telegram não está conectado.")
    if type == "cpf" and base and base not in CPF_BASES:
        raise HTTPException(status_code=400, detail=f"Base inválida. Use: {', '.join(CPF_BASES)}")
    req_id = str(uuid.uuid4())
    req_event = asyncio.Event()
    active_requests[req_id] = {
        'type': type, 'value': value, 'event': req_event,
        'completed': False, 'last_msg': None, 'last_text': '', 'messages': []
    }
    try:
        group_entity = await client.get_input_entity(GROUP_ID)
        logger.info(f"📤 Enviando comando para o grupo: /{type} {value}")
        async with client.action(group_entity, 'typing'):
            await human_delay(1, 2)
            await client.send_message(group_entity, f"/{type} {value}")
        final_text = ""
        button_clicked = False
        last_message_text = ""
        for attempt in range(MAX_ATTEMPTS):
            try:
                req_event.clear()
                await asyncio.wait_for(req_event.wait(), timeout=TIMEOUT_PER_ATTEMPT)
                msg = active_requests[req_id]['last_msg']
                text = active_requests[req_id]['last_text']
                if text == last_message_text: continue
                last_message_text = text
                if is_maintenance_message(text):
                    return JSONResponse(content={"status": "maintenance", "message": "Base em manutenção", "raw_text": text})
                if type == "cpf" and base and msg.reply_markup and "Selecione a base" in text and not button_clicked:
                    found = False
                    for i, row in enumerate(msg.reply_markup.rows):
                        for j, button in enumerate(row.buttons):
                            b_text = button.text if hasattr(button, 'text') else str(button)
                            if match_button_text(b_text, base):
                                await human_delay(1, 2)
                                await msg.click(i, j)
                                button_clicked = True
                                found = True
                                break
                        if found: break
                    if not found:
                        return JSONResponse(content={"status": "error", "message": f"Base '{base}' não disponível"})
                    continue
                if is_final_response(text):
                    await asyncio.sleep(FINAL_CONFIRMATION_DELAY)
                    final_text = active_requests[req_id]['last_text']
                    break
            except asyncio.TimeoutError:
                if is_final_response(active_requests[req_id]['last_text']):
                    final_text = active_requests[req_id]['last_text']
                    break
                if attempt > 5: break
        if not final_text:
            raise HTTPException(status_code=504, detail="Timeout aguardando resposta do bot")
        result = parse_to_json(final_text, type)
        if result.get("telegraph_link"):
            try:
                from app.extractor import extract_telegraph_data
                logger.info(f"Extraindo dados do Telegraph: {result['telegraph_link']}")
                telegraph_results = await extract_telegraph_data(result["telegraph_link"])
                if telegraph_results:
                    formatted_results = [item.get("dados", {}) for item in telegraph_results]
                    result["resultados"] = formatted_results
                    result["total_resultados"] = len(formatted_results)
                    if formatted_results and not result.get("parsed"):
                        result["parsed"] = formatted_results[0]
            except Exception as e:
                logger.warning(f"Erro ao extrair Telegraph: {e}")
        response_data = {
            "status": "success",
            "source": "telegram",
            "tipo_consulta": result.get("tipo_consulta", type),
            "total_resultados": result.get("total_resultados"),
            "telegraph_link": result.get("telegraph_link"),
            "resultados": result.get("resultados", []),
            "parsed": result.get("parsed", {}),
            "sections": result.get("sections", {}),
            "raw_text": result.get("raw_text", "")
        }
        save_to_cache(type, value, response_data, base)
        return JSONResponse(content=response_data)
    except Exception as e:
        logger.error(f"❌ Erro: {e}", exc_info=True)
        return JSONResponse(content={"status": "error", "message": str(e)}, status_code=500)
    finally:
        if req_id in active_requests:
            active_requests[req_id]['completed'] = True
            del active_requests[req_id]

# Configuração do TelegramClient
client = TelegramClient(
    StringSession(SESSION_STRING), API_ID, API_HASH,
    device_model=DEVICE_MODEL, system_version=SYSTEM_VERSION, app_version=APP_VERSION
)

@client.on(events.NewMessage(chats=GROUP_ID, from_users=TARGET_BOT_ID))
@client.on(events.MessageEdited(chats=GROUP_ID, from_users=TARGET_BOT_ID))
async def handle_bot_message(event):
    text = event.message.text or ""
    for req_id, req_data in active_requests.items():
        if not req_data['completed']:
            req_data['last_msg'] = event.message
            req_data['last_text'] = text
            req_data['messages'].append({'text': text, 'id': event.message.id})
            req_data['event'].set()

@asynccontextmanager
async def lifespan(app: FastAPI):
    global telegram_connected
    ensure_storage()
    try:
        await client.connect()
        if await client.is_user_authorized():
            telegram_connected = True
            logger.info("✅ Telegram Conectado")
        else:
            logger.warning("⚠️ Telegram não autorizado - Modo Cache-Only")
    except Exception as e:
        logger.error(f"❌ Erro conexão: {e}")
    yield
    await client.disconnect()

app = FastAPI(title="Telegram Consultas API", version="3.0", lifespan=lifespan, docs_url=None, redoc_url=None)

@app.get("/")
async def root():
    return {
        "status": "online",
        "telegram_connected": telegram_connected,
        "supported_types": VALID_TYPES,
        "documentation": {
            "swagger_json": "/swagger.json",
            "description": "OpenAPI 3.0 specification for this API"
        }
    }

@app.get("/swagger.json")
async def swagger_json():
    """Retorna a especificação OpenAPI 3.0 do arquivo Docs/swagger.json"""
    swagger_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "Docs", "swagger.json")
    try:
        with open(swagger_path, "r", encoding="utf-8") as f:
            swagger_content = json.load(f)
        return JSONResponse(content=swagger_content)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Arquivo swagger.json não encontrado em Docs/")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao carregar swagger.json: {str(e)}")

@app.get("/api/consultas")
async def consulta_get(type: str, value: str, base: Optional[str] = None):
    return await process_consulta(type, value, base)

@app.post("/api/consultas")
async def consulta_post(request: ConsultaRequest):
    return await process_consulta(request.type, request.value, request.base)

if __name__ == "__main__":
    import uvicorn
    from app.config import HOST, PORT
    uvicorn.run(app, host=HOST, port=PORT)

import os
from typing import Dict, List

# Credenciais Telegram (API_ID e API_HASH obtidos em my.telegram.org)
API_ID = 39564885
API_HASH = '6650a2e13cce447c6ba063ea3309e1eb'

# Session String (gere uma nova em: https://my.telegram.org)
SESSION_STRING = "1AZWarzUBu40WaTjeQxUWVvP5OmNhfsJg83_PupMWBOlMY4GfXiqIPTiFQWgT5O1NGlAbJkANT6I1BeeGfFEeoCvN25rWTAwlLZ5Y4oloy8ak4KdtaUmZkuxPDJhcBJIVbksihNiZbidehtkPymn4d1vEj-Tz_iGUDfKVJiTqUQtRWM20W-UIQSP0KMdmRe2oU2kC2gjT0bQOGVxwGx-xPbmhQeiOqSl2qi19kXhXk2wPSUwUN1dToD6ouSVh-5_MG4cbwjL_eKyZH6wO520mDH8H0G-1BO272uRhTQzMg0ulszyoOJ7SeX0tIkd_u2GnbH9Fva_9bCRoa5J_G2cSF3VLx0XfJvM="

# Bot alvo
TARGET_BOT_USERNAME = "@EmonNullbot"
TARGET_BOT_ID = 8437369390

# Grupo para consultas (替代DM，因为DM现在是付费的)
GROUP_ID = -1003538244823

# Configurações de dispositivo (simulação de app real)
DEVICE_MODEL = "iPhone 15 Pro"
SYSTEM_VERSION = "iOS 17.2"
APP_VERSION = "10.3.1"

# Configurações do servidor
HOST = "0.0.0.0"
PORT = int(os.environ.get("PORT", 8080))

# Diretório de armazenamento - ajustado para a nova estrutura
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE_STORAGE_DIR = os.path.join(BASE_DIR, "storage")

# Mapeamento de pastas de cache
FOLDER_MAP: Dict[str, str] = {
    "cpf": "CPFs",
    "ip": "IPs",
    "bin": "BINs",
    "nome": "Nomes",
    "telefone": "Telefones",
    "placa": "Placas",
    "cep": "CEPs",
    "cnpj": "CNPJs"
}

# Tipos de consulta válidos
VALID_TYPES: List[str] = ["cpf", "ip", "bin", "nome", "telefone", "placa", "cep", "cnpj"]

# Bases disponíveis para CPF
CPF_BASES: List[str] = ["local", "sisreg", "credlink"]

# Aliases para bases de CPF
BASE_ALIASES: Dict[str, List[str]] = {
    "local": ["base local", "local", "baselocal"],
    "sisreg": ["sisregi", "sisreg-iii", "sisreg iii", "sisregiii"],
    "credlink": ["credlink", "cred link"],
}

# Palavras-chave de processamento (respostas não finais)
PROCESSING_KEYWORDS: List[str] = [
    "Consultando",
    "Processando",
    "Aguarde",
    "Carregando",
    "Selecione a base",
    "__Processando sua solicitação",
]

# Indicadores de resposta final
FINAL_INDICATORS: List[str] = [
    "🕵️ CONSULTA",
    "° CPF:",
    "° IP Pesquisado:",
    "° BIN:",
    "° Nome:",
    "Manutenção",
    "° PAÍS / MOEDA",  # BIN
    "° PAÍS:",  # IP
    "° NOME:",  # SISREG
    "🕵️ CONSULTA DE NOME",  # Consulta de nome
    "🕵️ CONSULTA DE TELEFONE",  # Consulta de telefone
    "🔎 Telefone:",  # Consulta de telefone
    "• RESULTADO",  # Consulta de nome
    "✅ Consulta concluída.",
    "Total de resultados:",
    "Abrir relatório completo no Telegraph",
]

# Indicadores de manutenção
MAINTENANCE_INDICATORS: List[str] = [
    "Manutenção",
    "manutenção",
    "Em manutenção",
]

# Tempo de atraso humano (em segundos) - REDUZIDO PARA MAIS RAPIDEZ
HUMAN_DELAY_MIN = 0.5
HUMAN_DELAY_MAX = 2.0

# Número máximo de tentativas
MAX_ATTEMPTS = 50

# Timeout por tentativa (em segundos)
TIMEOUT_PER_ATTEMPT = 30

# Delay de confirmação final (em segundos)
FINAL_CONFIRMATION_DELAY = 3

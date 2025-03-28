import nest_asyncio
import asyncio
import gspread
import json
import os
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    CallbackContext,
    ConversationHandler
)
from dotenv import load_dotenv

# Carrega variáveis de ambiente
load_dotenv()

# Configurações
TOKEN = os.getenv('TELEGRAM_TOKEN')
SHEET_NAME = "Controle de Gastos"

# Estados para a conversa
DESCRICAO, VALOR, CATEGORIA = range(3)

# Categorias e configurações
CATEGORIAS = {
    "COMUNICAÇÃO": {"limite": 0, "emoji": "📞"},
    "MERCADO": {"limite": 0, "emoji": "🛒"},
    "BELEZA": {"limite": 0, "emoji": "💅"},
    "COMBUSTÍVEL": {"limite": 0, "emoji": "⛽"},
    "CELULA": {"limite": 0, "emoji": "📱"},
    "LAZER": {"limite": 0, "emoji": "🎮"},
    "DOCUMENTAÇÃO CARRO": {"limite": 0, "emoji": "🚗"},
    "IMPREVISTO": {"limite": 0, "emoji": "⚠️"}
}

# Inicialização do Google Sheets
def init_google_sheets():
    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive"
    ]
    
    # Obtém as credenciais da variável de ambiente
    credenciais_json = os.getenv('GOOGLE_CREDS_JSON')
    if not credenciais_json:
        raise ValueError("Variável GOOGLE_CREDS_JSON não encontrada")
    
    # Converte a string JSON para dicionário
    credenciais = json.loads(credenciais_json)
    
    creds = ServiceAccountCredentials.from_json_keyfile_dict(credenciais, scope)
    client = gspread.authorize(creds)
    return client.open(SHEET_NAME).sheet1

# Inicializa a planilha
try:
    sheet = init_google_sheets()
except Exception as e:
    print(f"Erro ao conectar ao Google Sheets: {str(e)}")
    sheet = None

async def start(update: Update, context: CallbackContext) -> None:
    """Envia mensagem de boas-vindas e instruções."""
    welcome_message = (
        "💰 *Bem-vindo ao Gestor de Gastos Pessoais!* 💰\n\n"
        "📌 *Como registrar um gasto:*\n"
        "1. Use /novogasto e siga as instruções\n"
        "OU\n"
        "Envie no formato: 'descrição - valor - categoria'\n\n"
        "🔧 *Outros comandos disponíveis:*\n"
        "/limite [categoria] [valor] - Define um limite para a categoria\n"
        "/saldo [categoria] - Consulta o saldo restante\n"
        "/relatorio - Gera um relatório de gastos\n"
        "/categorias - Lista todas as categorias disponíveis\n\n"
        "📊 *Categorias disponíveis:*\n" +
        "\n".join([f"{cat} {CATEGORIAS[cat]['emoji']}" for cat in CATEGORIAS])
    )
    
    await update.message.reply_text(welcome_message, parse_mode="Markdown")

# [Restante das funções permanece EXATAMENTE IGUAL...]
# (Mantenha todas as outras funções como estão, sem alterações)

def main():
    """Inicia o bot."""
    if not TOKEN:
        print("Erro: Token do Telegram não encontrado!")
        return
    
    if sheet is None:
        print("Erro: Não foi possível conectar ao Google Sheets!")
        return
    
    # Criar a aplicação
    app = Application.builder().token(TOKEN).build()
    
    # Configurar handlers
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("novogasto", start_novo_gasto)],
        states={
            DESCRICAO: [MessageHandler(filters.TEXT & ~filters.COMMAND, receber_descricao)],
            VALOR: [MessageHandler(filters.TEXT & ~filters.COMMAND, receber_valor)],
            CATEGORIA: [MessageHandler(filters.TEXT & ~filters.COMMAND, receber_categoria)],
        },
        fallbacks=[CommandHandler("cancelar", cancelar)],
    )
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(conv_handler)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, receber_gasto_rapido))
    app.add_handler(CommandHandler("limite", configurar_limite))
    app.add_handler(CommandHandler("saldo", consultar_saldo))
    app.add_handler(CommandHandler("relatorio", gerar_relatorio))
    app.add_handler(CommandHandler("categorias", listar_categorias))
    
    print("Bot está rodando...")
    nest_asyncio.apply()
    asyncio.run(app.run_polling())

if __name__ == "__main__":
    main()

import asyncio
import json
import os
from fastapi import FastAPI, Request
import uvicorn
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
import firebase_admin
from firebase_admin import credentials, db

# --------------------------------------------------
# Configuração Inicial
# --------------------------------------------------
load_dotenv()  # Carrega variáveis de ambiente primeiro

# Configurações
TOKEN = os.getenv('TELEGRAM_TOKEN')
FIREBASE_CONFIG = {
    "databaseURL": os.getenv('FIREBASE_DB_URL')
}

# Inicializa o Firebase
def init_firebase():
    try:
        firebase_creds = os.getenv('FIREBASE_CREDS_JSON')
        if not firebase_creds:
            raise ValueError("Variável FIREBASE_CREDS_JSON não encontrada")
            
        cred_dict = json.loads(firebase_creds)
        cred = credentials.Certificate(cred_dict)
        
        return firebase_admin.initialize_app(cred, FIREBASE_CONFIG)
    except Exception as e:
        print(f"Erro ao conectar ao Firebase: {str(e)}")
        return None

firebase_app = init_firebase()
firebase_ref = db.reference() if firebase_app else None

# --------------------------------------------------
# Configuração do FastAPI
# --------------------------------------------------
web_app = FastAPI()

@web_app.post("/webhook")
async def telegram_webhook(request: Request):
    """Endpoint para receber atualizações do Telegram"""
    try:
        # Acessa a instância do bot através do estado do FastAPI
        telegram_app = request.app.state.telegram_app
        
        update_data = await request.json()
        update = Update.de_json(update_data, telegram_app.bot)
        await telegram_app.process_update(update)
        return {"status": "success"}
    except Exception as e:
        print(f"Erro no webhook: {str(e)}")
        return {"status": "error"}

@web_app.get("/", status_code=200)
@web_app.head("/", status_code=200)
def status():
    return {"status": "Bot online!"}

# Carrega variáveis de ambiente
load_dotenv()

# Configurações
TOKEN = os.getenv('TELEGRAM_TOKEN')
FIREBASE_CONFIG = {
    "databaseURL": os.getenv('FIREBASE_DB_URL')
}

# Estados para a conversa
DESCRICAO, VALOR, CATEGORIA = range(3)

# Inicialização do Firebase
def init_firebase():
    try:
        # Obter as credenciais da variável de ambiente
        firebase_creds = os.getenv('FIREBASE_CREDS_JSON')
        if not firebase_creds:
            raise ValueError("Variável FIREBASE_CREDS_JSON não encontrada")
            
        cred_dict = json.loads(firebase_creds)
        cred = credentials.Certificate(cred_dict)
        
        # Inicializa o app do Firebase
        firebase_admin.initialize_app(cred, FIREBASE_CONFIG)
        
        print("Conexão com Firebase estabelecida com sucesso!")
        return db.reference()
    except Exception as e:
        print(f"Erro ao conectar ao Firebase: {str(e)}")
        return None

# Inicializa o Firebase
firebase_ref = init_firebase()

# Função auxiliar para obter limites
async def get_limite(categoria: str) -> float:
    snapshot = firebase_ref.child('limites').child(categoria).get()
    return float(snapshot) if snapshot else 0.0
# Função Cancelar
async def cancelar(update: Update, context: CallbackContext) -> int:
    """Cancela a operação em andamento"""
    await update.message.reply_text("❌ Operação cancelada com sucesso!")
    context.user_data.clear()
    return ConversationHandler.END

# Função auxiliar para salvar limite
async def set_limite(categoria: str, valor: float):
    firebase_ref.child('limites').child(categoria).set(valor)

# Categorias e emojis
CATEGORIAS = {
    "COMUNICAÇÃO": "📞",
    "MERCADO": "🛒",
    "BELEZA": "💅",
    "COMBUSTÍVEL": "⛽",
    "CELULA": "📱",
    "LAZER": "🎮",
    "DOCUMENTAÇÃO CARRO": "🚗",
    "IMPREVISTO": "⚠️"
}

async def start(update: Update, context: CallbackContext) -> None:
    """Envia mensagem de boas-vindas"""
    welcome_msg = (
        "💰 *Bem-vindo ao Gestor de Gastos!* 💰\n\n"
        "📌 *Comandos disponíveis:*\n"
        "/novogasto - Registrar novo gasto\n"
        "/limite [categoria] [valor] - Definir limite\n"
        "/saldo [categoria] - Ver saldo\n"
        "/relatorio - Gerar relatório\n"
        "/categorias - Listar categorias\n\n"
        "⚡ *Dados armazenados em tempo real com Firebase*"
    )
    await update.message.reply_text(welcome_msg, parse_mode="Markdown")

async def start_novo_gasto(update: Update, context: CallbackContext) -> int:
    """Inicia o registro de novo gasto"""
    await update.message.reply_text("📝 Digite a descrição do gasto:")
    return DESCRICAO

async def receber_descricao(update: Update, context: CallbackContext) -> int:
    """Armazena descrição"""
    context.user_data['descricao'] = update.message.text
    await update.message.reply_text("💵 Digite o valor (ex: 150.50):")
    return VALOR

async def receber_valor(update: Update, context: CallbackContext) -> int:
    """Valida e armazena valor"""
    try:
        valor = float(update.message.text.replace(',', '.'))
        if valor <= 0:
            raise ValueError
        context.user_data['valor'] = valor
        
        # Cria teclado com categorias
        keyboard = [[cat] for cat in CATEGORIAS]
        await update.message.reply_text(
            "🏷️ Selecione a categoria:",
            reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True)
        )
        return CATEGORIA
    except:
        await update.message.reply_text("❌ Valor inválido! Digite novamente:")
        return VALOR

async def receber_categoria(update: Update, context: CallbackContext) -> int:
    """Armazena categoria e salva no Firebase"""
    categoria = update.message.text.upper()
    if categoria not in CATEGORIAS:
        await update.message.reply_text("❌ Categoria inválida! Selecione:")
        return CATEGORIA
    
    # Obter dados do contexto
    descricao = context.user_data['descricao']
    valor = context.user_data['valor']
    data = datetime.now().isoformat()
    
    try:
        # Salvar no Firebase
        gasto_data = {
            'descricao': descricao,
            'valor': valor,
            'categoria': categoria,
            'data': data,
            'user_id': update.message.from_user.id
        }
        
        # Push para novo nó
        firebase_ref.child('gastos').push().set(gasto_data)
        
        # Calcular saldo
        limite = await get_limite(categoria)
        gastos_ref = firebase_ref.child('gastos').order_by_child('categoria').equal_to(categoria)
        snapshot = gastos_ref.get()
        total_gasto = sum(item['valor'] for item in snapshot.values()) if snapshot else 0
        
        resposta = (
            f"✅ *Gasto registrado!*\n\n"
            f"📝 {descricao}\n"
            f"💵 R$ {valor:.2f}\n"
            f"🏷️ {categoria} {CATEGORIAS[categoria]}\n"
            f"💰 Saldo: R$ {limite - total_gasto:.2f} / {limite:.2f}"
        )
        
        await update.message.reply_text(resposta, parse_mode="Markdown")
        return ConversationHandler.END
        
    except Exception as e:
        await update.message.reply_text(f"🔥 Erro no Firebase: {str(e)}")
        return ConversationHandler.END

async def configurar_limite(update: Update, context: CallbackContext) -> None:
    """Define limite para categoria"""
    try:
        if len(context.args) != 2:
            raise ValueError("Formato: /limite [categoria] [valor]")
        
        categoria = context.args[0].upper()
        if categoria not in CATEGORIAS:
            raise ValueError("Categoria inválida")
            
        limite = float(context.args[1])
        await set_limite(categoria, limite)
        
        await update.message.reply_text(
            f"✅ Limite de {categoria} definido para R$ {limite:.2f}",
            parse_mode="Markdown"
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Erro: {str(e)}")

async def consultar_saldo(update: Update, context: CallbackContext) -> None:
    """Exibe saldo da categoria"""
    try:
        categoria = context.args[0].upper()
        if categoria not in CATEGORIAS:
            raise ValueError("Categoria inválida")
            
        limite = await get_limite(categoria)
        gastos_ref = firebase_ref.child('gastos').order_by_child('categoria').equal_to(categoria)
        snapshot = gastos_ref.get()
        total = sum(item['valor'] for item in snapshot.values()) if snapshot else 0
        
        resposta = (
            f"📊 *Saldo {categoria}*\n\n"
            f"🏦 Limite: R$ {limite:.2f}\n"
            f"💸 Gasto: R$ {total:.2f}\n"
            f"💎 Saldo: R$ {limite - total:.2f}\n"
            f"📆 Atualizado em: {datetime.now().strftime('%d/%m %H:%M')}"
        )
        
        await update.message.reply_text(resposta, parse_mode="Markdown")
    except Exception as e:
        await update.message.reply_text(f"❌ Erro: {str(e)}")

async def gerar_relatorio(update: Update, context: CallbackContext) -> None:
    """Gera relatório completo"""
    try:
        # Obter limites
        limites_ref = firebase_ref.child('limites').get()
        limites = {cat: float(limite) for cat, limite in limites_ref.items()} if limites_ref else {}
        
        # Obter gastos
        gastos_ref = firebase_ref.child('gastos').get()
        gastos = gastos_ref if gastos_ref else {}
        
        # Processar dados
        resumo = {}
        for key, item in gastos.items():
            cat = item['categoria']
            resumo[cat] = resumo.get(cat, 0) + item['valor']
        
        # Construir relatório
        report = "📊 *Relatório Completo*\n\n"
        total_gasto = 0
        total_limite = 0
        
        for cat in CATEGORIAS:
            emoji = CATEGORIAS[cat]
            gasto = resumo.get(cat, 0)
            limite = limites.get(cat, 0)
            
            report += (
                f"{emoji} *{cat}*\n"
                f"▫️ Gasto: R$ {gasto:.2f}\n"
                f"▫️ Limite: R$ {limite:.2f}\n"
                f"▫️ Saldo: R$ {limite - gasto:.2f}\n\n"
            )
            
            total_gasto += gasto
            total_limite += limite
        
        report += (
            f"💵 *Total Gasto:* R$ {total_gasto:.2f}\n"
            f"🏦 *Total Limite:* R$ {total_limite:.2f}\n"
            f"💎 *Saldo Total:* R$ {total_limite - total_gasto:.2f}"
        )
        
        await update.message.reply_text(report, parse_mode="Markdown")
    except Exception as e:
        await update.message.reply_text(f"❌ Erro: {str(e)}")

async def listar_categorias(update: Update, context: CallbackContext) -> None:
    """Lista todas as categorias"""
    resposta = "🏷️ *Categorias Disponíveis:*\n\n"
    for cat, emoji in CATEGORIAS.items():
        resposta += f"{emoji} {cat}\n"
    resposta += "\nUse /limite para definir valores"
    await update.message.reply_text(resposta, parse_mode="Markdown")

async def main() -> None:
    """Configura e inicia o bot com webhook"""
    if not TOKEN:
        raise ValueError("Token do Telegram não configurado!")
    
    if not firebase_ref:
        raise ValueError("Falha na conexão com Firebase!")

    # URL completa do webhook
    WEBHOOK_URL = "https://gestorjuliusbot.onrender.com/webhook"
    
    # Cria aplicação do Telegram
    telegram_app = Application.builder().token(TOKEN).build()
    
    # Armazena no estado do FastAPI
    web_app.state.telegram_app = telegram_app
    
    # Configura handlers
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('novogasto', start_novo_gasto)],
        states={
            DESCRICAO: [MessageHandler(filters.TEXT, receber_descricao)],
            VALOR: [MessageHandler(filters.TEXT, receber_valor)],
            CATEGORIA: [MessageHandler(filters.TEXT, receber_categoria)]
        },
        fallbacks=[CommandHandler('cancelar', cancelar)]
    )
    
    telegram_app.add_handler(CommandHandler("start", start))
    telegram_app.add_handler(conv_handler)
    telegram_app.add_handler(CommandHandler("limite", configurar_limite))
    telegram_app.add_handler(CommandHandler("saldo", consultar_saldo))
    telegram_app.add_handler(CommandHandler("relatorio", gerar_relatorio))
    telegram_app.add_handler(CommandHandler("categorias", listar_categorias))

    # Configura webhook
    await telegram_app.bot.set_webhook(
        url=WEBHOOK_URL,
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True
    )

    # Inicia servidor
    server = uvicorn.Server(
        config=uvicorn.Config(
            app=web_app,
            host="0.0.0.0",
            port=8000,
            use_colors=False
        )
    )

    await server.serve()

if __name__ == "__main__":
    asyncio.run(main())

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

async def start_novo_gasto(update: Update, context: CallbackContext) -> int:
    """Inicia o processo de registro de um novo gasto."""
    await update.message.reply_text("Por favor, digite a descrição do gasto:")
    return DESCRICAO

async def receber_descricao(update: Update, context: CallbackContext) -> int:
    """Armazena a descrição e pede o valor."""
    context.user_data['descricao'] = update.message.text
    await update.message.reply_text("Agora, digite o valor do gasto (apenas números, use ponto para decimais):")
    return VALOR

async def receber_valor(update: Update, context: CallbackContext) -> int:
    """Armazena o valor e pede a categoria."""
    try:
        valor = float(update.message.text)
        if valor <= 0:
            await update.message.reply_text("O valor deve ser maior que zero. Por favor, digite novamente:")
            return VALOR
        
        context.user_data['valor'] = valor
        
        # Cria teclado com categorias
        keyboard = [[cat] for cat in CATEGORIAS]
        reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True)
        
        await update.message.reply_text(
            "Selecione a categoria:",
            reply_markup=reply_markup
        )
        return CATEGORIA
    except ValueError:
        await update.message.reply_text("Valor inválido. Por favor, digite apenas números (ex: 150.50):")
        return VALOR

async def receber_categoria(update: Update, context: CallbackContext) -> int:
    """Armazena a categoria e registra o gasto."""
    categoria = update.message.text.upper()
    
    if categoria not in CATEGORIAS:
        await update.message.reply_text("Categoria inválida. Por favor, selecione uma das opções:")
        return CATEGORIA
    
    # Registrar o gasto
    descricao = context.user_data['descricao']
    valor = context.user_data['valor']
    data_atual = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    limite = CATEGORIAS[categoria]["limite"]
    
    sheet.append_row([data_atual, descricao, valor, categoria, limite])
    
    # Calcular saldo restante
    gastos_categoria = sum(float(row[2]) for row in sheet.get_all_values() if len(row) > 3 and row[3].strip().upper() == categoria)
    saldo_restante = limite - gastos_categoria
    
    response = (
        f"✅ *Gasto registrado com sucesso!*\n\n"
        f"📝 *Descrição:* {descricao}\n"
        f"💵 *Valor:* R$ {valor:.2f}\n"
        f"🏷️ *Categoria:* {categoria} {CATEGORIAS[categoria]['emoji']}\n"
        f"📅 *Data:* {data_atual}\n\n"
        f"💰 *Saldo restante:* R$ {saldo_restante:.2f} / R$ {limite:.2f}"
    )
    
    await update.message.reply_text(response, parse_mode="Markdown")
    context.user_data.clear()
    return ConversationHandler.END

async def cancelar(update: Update, context: CallbackContext) -> int:
    """Cancela o processo de registro."""
    await update.message.reply_text("Registro de gasto cancelado.")
    context.user_data.clear()
    return ConversationHandler.END

async def receber_gasto_rapido(update: Update, context: CallbackContext) -> None:
    """Processa mensagens no formato rápido: descrição - valor - categoria."""
    mensagem = update.message.text
    try:
        partes = [part.strip() for part in mensagem.split("-", 2)]
        if len(partes) != 3:
            raise ValueError("Formato inválido. Use: 'descrição - valor - categoria'")
        
        descricao, valor_str, categoria = partes
        valor = float(valor_str)
        categoria = categoria.upper()
        
        if categoria not in CATEGORIAS:
            raise ValueError(f"Categoria inválida. Opções: {', '.join(CATEGORIAS.keys())}")
        
        if valor <= 0:
            raise ValueError("O valor deve ser maior que zero")
        
        # Registrar o gasto
        data_atual = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        limite = CATEGORIAS[categoria]["limite"]
        sheet.append_row([data_atual, descricao, valor, categoria, limite])
        
        # Calcular saldo restante
        gastos_categoria = sum(float(row[2]) for row in sheet.get_all_values() if len(row) > 3 and row[3].strip().upper() == categoria)
        saldo_restante = limite - gastos_categoria
        
        response = (
            f"✅ *Gasto registrado com sucesso!*\n\n"
            f"📝 *Descrição:* {descricao}\n"
            f"💵 *Valor:* R$ {valor:.2f}\n"
            f"🏷️ *Categoria:* {categoria} {CATEGORIAS[categoria]['emoji']}\n\n"
            f"💰 *Saldo restante:* R$ {saldo_restante:.2f} / R$ {limite:.2f}"
        )
        
        await update.message.reply_text(response, parse_mode="Markdown")
    except ValueError as e:
        await update.message.reply_text(f"❌ Erro: {str(e)}")
    except Exception as e:
        await update.message.reply_text(f"❌ Ocorreu um erro inesperado: {str(e)}")

async def configurar_limite(update: Update, context: CallbackContext) -> None:
    """Configura o limite para uma categoria específica."""
    try:
        if len(context.args) != 2:
            raise ValueError("Formato inválido. Use: /limite [categoria] [valor]")
        
        categoria = context.args[0].upper()
        limite = float(context.args[1])
        
        if categoria not in CATEGORIAS:
            raise ValueError(f"Categoria inválida. Opções: {', '.join(CATEGORIAS.keys())}")
        
        if limite < 0:
            raise ValueError("O limite não pode ser negativo")
        
        CATEGORIAS[categoria]["limite"] = limite
        
        # Atualizar limites em gastos existentes (opcional)
        all_values = sheet.get_all_values()
        for i, row in enumerate(all_values[1:], start=2):  # Pular cabeçalho
            if len(row) > 3 and row[3].strip().upper() == categoria:
                sheet.update_cell(i, 5, limite)  # Coluna 5 é a coluna de limite
        
        await update.message.reply_text(
            f"✅ Limite atualizado para {categoria} {CATEGORIAS[categoria]['emoji']}:\n"
            f"Novo limite: R$ {limite:.2f}"
        )
    except ValueError as e:
        await update.message.reply_text(f"❌ Erro: {str(e)}")
    except Exception as e:
        await update.message.reply_text(f"❌ Ocorreu um erro inesperado: {str(e)}")

async def consultar_saldo(update: Update, context: CallbackContext) -> None:
    """Consulta o saldo de uma categoria específica."""
    try:
        if not context.args:
            raise ValueError("Por favor, especifique uma categoria")
        
        categoria = context.args[0].upper()
        if categoria not in CATEGORIAS:
            raise ValueError(f"Categoria inválida. Opções: {', '.join(CATEGORIAS.keys())}")
        
        limite = CATEGORIAS[categoria]["limite"]
        gastos_categoria = sum(
            float(row[2]) for row in sheet.get_all_values() 
            if len(row) > 3 and row[3].strip().upper() == categoria
        )
        saldo_restante = limite - gastos_categoria
        percentual = (gastos_categoria / limite * 100) if limite > 0 else 0
        
        barra_progresso = ""
        if limite > 0:
            completado = min(int(percentual / 10), 10)
            barra_progresso = "\n[" + "🟩" * completado + "🟥" * (10 - completado) + "]"
        
        response = (
            f"💰 *Saldo da categoria {categoria} {CATEGORIAS[categoria]['emoji']}*\n\n"
            f"💵 *Gasto total:* R$ {gastos_categoria:.2f}\n"
            f"🏦 *Limite definido:* R$ {limite:.2f}\n"
            f"💎 *Saldo restante:* R$ {saldo_restante:.2f}\n"
            f"📊 *Percentual usado:* {percentual:.1f}%{barra_progresso}"
        )
        
        await update.message.reply_text(response, parse_mode="Markdown")
    except ValueError as e:
        await update.message.reply_text(f"❌ Erro: {str(e)}")
    except Exception as e:
        await update.message.reply_text(f"❌ Ocorreu um erro inesperado: {str(e)}")

async def gerar_relatorio(update: Update, context: CallbackContext) -> None:
    """Gera um relatório resumido dos gastos."""
    try:
        # Obter todos os dados da planilha
        all_values = sheet.get_all_values()
        
        if len(all_values) <= 1:  # Assumindo que a primeira linha é cabeçalho
            await update.message.reply_text("Nenhum gasto registrado ainda.")
            return
        
        # Calcular totais por categoria
        totais = {categoria: 0 for categoria in CATEGORIAS}
        for row in all_values[1:]:  # Pular cabeçalho
            try:
                if len(row) > 3:
                    categoria = row[3].strip().upper()
                    valor = float(row[2])
                    if categoria in totais:
                        totais[categoria] += valor
            except (IndexError, ValueError):
                continue
        
        # Calcular totais gerais
        total_gasto = sum(totais.values())
        total_limite = sum(CATEGORIAS[cat]["limite"] for cat in CATEGORIAS)
        saldo_total = total_limite - total_gasto
        
        # Construir mensagem do relatório
        relatorio = "📊 *RELATÓRIO DE GASTOS* 📊\n\n"
        relatorio += f"📅 *Período:* Todos os registros\n"
        relatorio += f"💰 *Total gasto:* R$ {total_gasto:.2f}\n"
        relatorio += f"🏦 *Total limite:* R$ {total_limite:.2f}\n"
        relatorio += f"💵 *Saldo total:* R$ {saldo_total:.2f}\n\n"
        relatorio += "*Detalhes por categoria:*\n"
        
        for categoria in sorted(CATEGORIAS.keys()):
            emoji = CATEGORIAS[categoria]["emoji"]
            limite = CATEGORIAS[categoria]["limite"]
            gasto = totais[categoria]
            percentual = (gasto / limite * 100) if limite > 0 else 0
            barra = "🟢" if percentual < 50 else "🟡" if percentual < 80 else "🔴"
            
            relatorio += (
                f"\n{emoji} *{categoria}:*\n"
                f"Gasto: R$ {gasto:.2f} / Limite: R$ {limite:.2f}\n"
                f"Saldo: R$ {limite - gasto:.2f} ({percentual:.1f}% usado) {barra}"
            )
        
        await update.message.reply_text(relatorio, parse_mode="Markdown")
    except Exception as e:
        await update.message.reply_text(f"❌ Erro ao gerar relatório: {str(e)}")

async def listar_categorias(update: Update, context: CallbackContext) -> None:
    """Lista todas as categorias disponíveis com seus limites."""
    response = "🏷️ *Categorias disponíveis:*\n\n"
    for categoria, dados in CATEGORIAS.items():
        response += (
            f"{dados['emoji']} *{categoria}*\n"
            f"Limite: R$ {dados['limite']:.2f}\n\n"
        )
    await update.message.reply_text(response, parse_mode="Markdown")

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

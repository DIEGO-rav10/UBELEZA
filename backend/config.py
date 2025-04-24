import os
from dotenv import load_dotenv

# Carrega variáveis do arquivo .env para o ambiente
load_dotenv()

class Config:
    """Configurações base do Flask."""
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'uma-chave-secreta-muito-dificil-de-adivinhar' # Mude isso em produção!

    # Configuração do SQLAlchemy
    # Usa a variável DATABASE_URL do .env ou um SQLite padrão para desenvolvimento fácil
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or \
        'sqlite:///' + os.path.join(os.path.abspath(os.path.dirname(__file__)), 'app.db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False # Desativa warnings desnecessários

    # Configuração CORS (opcional, mas útil para desenvolvimento)
    # Permite que o frontend (ex: localhost:xxxx) acesse a API (localhost:5000)
    CORS_HEADERS = 'Content-Type'
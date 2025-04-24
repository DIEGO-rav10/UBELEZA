**Arquivo 7: `README.md` (Instruções)**

```markdown
# Ubeleza Calculadora v4.20.5 (Full-Stack com Flask e PostgreSQL)

Este projeto é uma calculadora financeira para motoristas, refatorada para usar um backend Python/Flask e um banco de dados PostgreSQL.

## Estrutura

*   `/backend`: Contém o código da API Flask.
*   `/frontend`: Contém o arquivo `Uber_contas.html` (interface do usuário).

## Pré-requisitos

*   **Python 3.8+** e **pip**: [https://www.python.org/](https://www.python.org/)
*   **PostgreSQL**: Um servidor PostgreSQL instalado e rodando. [https://www.postgresql.org/](https://www.postgresql.org/)
*   **Git** (opcional, para controle de versão): [https://git-scm.com/](https://git-scm.com/)
*   **Navegador Web Moderno** (Chrome, Firefox, Edge, etc.)

## Configuração do Banco de Dados PostgreSQL

1.  **Instale o PostgreSQL** se ainda não o tiver.
2.  **Crie um banco de dados** para a aplicação (você pode usar o `psql` ou uma ferramenta gráfica como pgAdmin):
    ```sql
    CREATE DATABASE db_ubeleza;
    ```
3.  **Crie um usuário** (role) para a aplicação e dê a ele permissões no banco de dados criado. **Lembre-se de usar uma senha segura!**
    ```sql
    CREATE USER user_ubeleza WITH PASSWORD 'password_ubeleza';
    GRANT ALL PRIVILEGES ON DATABASE db_ubeleza TO user_ubeleza;
    ```
    *Substitua `user_ubeleza` e `password_ubeleza` se desejar.*

## Configuração e Execução do Projeto

1.  **Clone o Repositório** (se estiver usando Git) ou baixe e extraia os arquivos para uma pasta (ex: `ubeleza-calculadora`).

2.  **Navegue até a pasta `backend`** no seu terminal:
    ```bash
    cd caminho/para/ubeleza-calculadora/backend
    ```

3.  **Crie e Ative um Ambiente Virtual** (altamente recomendado):
    ```bash
    # No Windows
    python -m venv venv
    .\venv\Scripts\activate

    # No macOS/Linux
    python3 -m venv venv
    source venv/bin/activate
    ```
    *(Você verá `(venv)` no início do prompt do terminal se estiver ativo).*

4.  **Instale as Dependências Python:**
    ```bash
    pip install -r requirements.txt
    ```

5.  **Configure as Variáveis de Ambiente:**
    *   Crie um arquivo chamado `.env` dentro da pasta `backend`.
    *   Copie o conteúdo abaixo para o arquivo `.env`:
        ```dotenv
        # Formato: postgresql://usuario:senha@host:porta/nome_banco
        DATABASE_URL=postgresql://user_ubeleza:password_ubeleza@localhost:5432/db_ubeleza

        # Gere uma chave secreta forte (ex: python -c 'import secrets; print(secrets.token_hex(16))')
        SECRET_KEY=coloque_sua_chave_secreta_forte_aqui
        ```
    *   **IMPORTANTE:** Atualize `DATABASE_URL` com o usuário, senha, host (geralmente `localhost`), porta (geralmente `5432`) e nome do banco que você criou no PostgreSQL.
    *   **IMPORTANTE:** Substitua `coloque_sua_chave_secreta_forte_aqui` por uma chave secreta real e segura.

6.  **Aplique as Migrações do Banco de Dados:**
    *   (Primeira vez apenas) Inicialize o sistema de migração:
        ```bash
        flask db init
        ```
    *   Gere o script de migração inicial baseado nos `models.py`:
        ```bash
        flask db migrate -m "Initial migration."
        ```
    *   Aplique a migração ao banco de dados (isso criará as tabelas):
        ```bash
        flask db upgrade
        ```
    *   *Se você modificar os `models.py` no futuro, repita os comandos `flask db migrate` e `flask db upgrade`.*

7.  **Execute o Servidor Flask (Backend):**
    ```bash
    flask run
    ```
    *   O terminal mostrará que o servidor está rodando, geralmente em `http://127.0.0.1:5000/`. Mantenha este terminal aberto.

8.  **Abra o Frontend:**
    *   Navegue até a pasta `frontend`.
    *   Abra o arquivo `Uber_contas.html` diretamente no seu navegador web (clique duas vezes nele ou use o menu "Abrir Arquivo" do navegador).

## Como Funciona

*   O backend Flask agora lida com toda a persistência de dados no PostgreSQL.
*   O frontend (`Uber_contas.html`) foi modificado para:
    *   Não usar mais o `localStorage` para dados principais (ciclos, corridas, despesas, arquivos).
    *   Carregar o estado inicial fazendo uma requisição `GET /api/state` ao backend.
    *   Enviar requisições (POST, PUT, DELETE) para a API Flask sempre que uma ação que modifica dados é realizada (adicionar corrida, iniciar ciclo, arquivar, etc.).
    *   Atualizar a interface do usuário com base na resposta recebida da API.
*   O `localStorage` ainda é usado no frontend para salvar o estado da UI (visibilidade das tabelas, etc.), pois isso não precisa ir para o backend.

## Solução de Problemas

*   **Erro de CORS:** Se o frontend reclamar sobre CORS, verifique se `CORS(app)` está presente em `backend/app.py` e se o servidor Flask foi reiniciado após adicionar/modificar.
*   **Erro de Conexão com Banco:** Verifique se o servidor PostgreSQL está rodando e se a `DATABASE_URL` no arquivo `.env` está correta (usuário, senha, host, porta, nome do banco).
*   **Erro 500 Internal Server Error:** Verifique o log no terminal onde o `flask run` está executando. Ele geralmente mostra detalhes sobre erros no código Python.
*   **API não responde:** Verifique se o servidor Flask está rodando (`flask run`) e se a `API_BASE_URL` no arquivo `Uber_contas.html` (`<script>` tag) está correta (`http://127.0.0.1:5000/api`).
```

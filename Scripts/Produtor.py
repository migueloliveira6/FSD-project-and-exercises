import socket
import json
import threading
import argparse
import os
import time

conexao = None  # Define conexao as a global variable

parser = argparse.ArgumentParser(description='Start the producer server.')
parser.add_argument('--port', type=int, default=5006, help='Port number to run the producer server on.')
args = parser.parse_args()

host = "10.8.0.4"
port = args.port

# Function to load products from a JSON file
def load_produtos(file_path):
    with open(file_path, 'r') as file:
        return json.load(file)

# Function to save products to a JSON file
def save_produtos(file_path, produtos):
    with open(file_path, 'w') as file:
        json.dump(produtos, file, indent=4)

# Get the directory of the current script
script_dir = os.path.dirname(os.path.abspath(__file__))

# Construct the path to the JSON file
produtos_file_path = os.path.join(script_dir, 'produtos.json')

# Load the initial list of products from the JSON file
produtos = load_produtos(produtos_file_path)

produtores = [
    {"host": "localhost", "port": 5005},
    {"host": "localhost", "port": 5004}
]

lock = threading.Lock()

# Função para enviar respostas ao cliente
def enviar_resposta(conexao, dados):
    conexao.sendall(json.dumps(dados).encode('utf-8'))

# Função para listar produtos com preço de revenda
def listar_produtos(conexao, categorias):
    with lock:
        response = {
            categoria: [
                {
                    "nome": produto["nome"],
                    "quantidade": produto["quantidade"],
                    "preco": produto["preco"],
                    "taxa_revenda": produto["taxa_revenda"]
                }
                for produto in produtos[categoria]
                if categoria in produtos
            ]
            for categoria in categorias if categoria in produtos
        }
    enviar_resposta(conexao, response)

# Função para comprar produto
def comprar(conexao, categoria, produto_nome, quantidade):
    categoria = categoria.strip().lower()
    produto_nome = produto_nome.strip().lower()

    with lock:
        if categoria in produtos:
            for produto in produtos[categoria]:
                if produto['nome'].strip().lower() == produto_nome:
                    if produto['quantidade'] >= quantidade:
                        produto['quantidade'] -= quantidade
                        save_produtos(produtos_file_path, produtos)  # Save the updated products
                        response = {
                            "status": "sucesso",
                            "mensagem": f"Compra de {quantidade} {produto_nome}(s) realizada com sucesso.",
                            "preco": produto["preco"],  # Preço do produto
                            "taxa_revenda": produto["taxa_revenda"]  # Taxa de revenda
                        }
                    else:
                        response = {
                            "status": "erro",
                            "mensagem": f"Quantidade insuficiente de {produto_nome}. Disponível: {produto['quantidade']}."
                        }
                    break
            else:
                response = {
                    "status": "erro",
                    "mensagem": f"Produto {produto_nome} não encontrado."
                }
        else:
            response = {
                "status": "erro",
                "mensagem": f"Categoria {categoria} não encontrada."
            }

    enviar_resposta(conexao, response)

# Função para listar categorias
def listar_categorias(conexao):
    with lock:
        response = list(produtos.keys())
    enviar_resposta(conexao, response)

# Função que lida com cada cliente
def handle_client(conexao, endereco):
    print(f"Conexão estabelecida com {endereco}")
    try:
        while True:
            data = conexao.recv(1024)
            if not data:
                break

            try:
                pedido = json.loads(data)
            except json.JSONDecodeError:
                enviar_resposta(conexao, {"status": "erro", "mensagem": "Dados inválidos."})
                continue

            tipo_pedido = pedido.get('type')
            print(f"Recebido pedido: {pedido}")

            if tipo_pedido == "listarProdutos":
                categorias = pedido.get('categorias', [])
                listar_produtos(conexao, categorias)

            elif tipo_pedido == "comprar":
                categoria = pedido.get('categoria')
                produto = pedido.get('produto')
                quantidade = pedido.get('quantidade')
                if categoria and produto and isinstance(quantidade, int):
                    comprar(conexao, categoria, produto, quantidade)
                else:
                    enviar_resposta(conexao, {"status": "erro", "mensagem": "Pedido de compra inválido."})

            elif tipo_pedido == "listarCategorias":
                listar_categorias(conexao)

            elif tipo_pedido == "desconectar":
                print(f"Marketplace {endereco} desconectado.")
                break

            else:
                enviar_resposta(conexao, {"status": "erro", "mensagem": "Pedido inválido."})

    except socket.error as e:
        print(f"Erro de socket: {e}")
    finally:
        conexao.close()

# Função para tentar conectar ao produtor
def conectar_produtor(host, port):
    try:
        cliente_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        cliente_socket.connect((host, port))
        return cliente_socket
    except socket.error as e:
        print(f"Erro ao conectar ao produtor em {host}:{port} - {e}")
        return None

# Função para tentar reconectar periodicamente a produtores indisponíveis
def monitorar_produtores(produtores):
    while True:
        for produtor in produtores:
            cliente_socket = conectar_produtor(produtor['host'], produtor['port'])
            if cliente_socket:
                print(f"Reconectado ao produtor em {produtor['host']}:{produtor['port']}")
            else:
                print(f"Produtor em {produtor['host']}:{produtor['port']} ainda indisponível.")
        time.sleep(5)  # Tentar reconectar a cada 5 segundos

# Função para iniciar o servidor
def iniciar_servidor(servidor_host, servidor_port):
    global conexao  # Use the global conexao variable
    servidor_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    servidor_socket.bind((servidor_host, servidor_port))
    servidor_socket.listen()
    print(f"Servidor iniciado em {servidor_host}:{servidor_port}")

    while True:
        conexao, endereco = servidor_socket.accept()
        threading.Thread(target=handle_client, args=(conexao, endereco)).start()

if __name__ == "__main__":
    threading.Thread(target=monitorar_produtores, args=(produtores,),
                     daemon=True).start()  # Monitorar produtores em segundo plano
    iniciar_servidor(host, port)
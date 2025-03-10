import socket
import json
import threading
import argparse
import os

# Argument parser for dynamic port assignment
parser = argparse.ArgumentParser(description='Start the producer server.')
parser.add_argument('--port', type=int, default=5005, help='Port number to run the producer server on.')
args = parser.parse_args()

host = "localhost"
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

lock = threading.Lock()

def calcular_preco_revenda(preco, taxa_revenda):
    return preco * (1 + taxa_revenda)

# Função para enviar respostas ao cliente (evita duplicação)
def enviar_resposta(conexao, dados):
    conexao.sendall(json.dumps(dados).encode('utf-8'))

# Função para obter produtos por categoria
def obter_produtos_por_categoria(categorias):
    produtos_disponiveis = {}
    for categoria in categorias:
        if categoria in produtos:
            produtos_disponiveis[categoria] = [
                {**produto, "preco_revenda": calcular_preco_revenda(produto["preco"], produto["taxa_revenda"])}
                for produto in produtos[categoria]
            ]
    return produtos_disponiveis

# Função para listar produtos
def listar_produtos(conexao, categorias):
    with lock:
        response = obter_produtos_por_categoria(categorias)
    enviar_resposta(conexao, response)

# Função para comprar produtos
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
                        response = {"status": "sucesso",
                                    "mensagem": f"Compra de {quantidade} {produto_nome}(s) realizada com sucesso."}
                    else:
                        response = {"status": "erro",
                                    "mensagem": f"Quantidade insuficiente de {produto_nome}. Disponível: {produto['quantidade']}."}
                    break
            else:
                response = {"status": "erro", "mensagem": f"Produto {produto_nome} não encontrado."}
        else:
            response = {"status": "erro", "mensagem": f"Categoria {categoria} não encontrada."}

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

# Função para iniciar o servidor
def iniciar_servidor(servidor_host, servidor_port):
    servidor_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    servidor_socket.bind((servidor_host, servidor_port))
    servidor_socket.listen()
    print(f"Servidor iniciado em {servidor_host}:{servidor_port}")

    while True:
        conexao, endereco = servidor_socket.accept()
        threading.Thread(target=handle_client, args=(conexao, endereco)).start()

if __name__ == "__main__":
    print("Produtos carregados:")
    print(json.dumps(produtos, indent=4))
    iniciar_servidor(host, port)
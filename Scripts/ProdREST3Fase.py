import argparse
import os
from flask import Flask, jsonify, request
import json
import requests
import threading
import time
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.backends import default_backend
from cryptography.x509 import load_pem_x509_certificate

app = Flask(__name__)

chave_privada = None
chave_publica = None
certificate = None

# Função para carregar produtos de um arquivo JSON
def load_produtos(file_path):
    with open(file_path, 'r') as file:
        return json.load(file)

# Caminho do script e do arquivo JSON
script_dir = os.path.dirname(os.path.abspath(__file__))
produtos_file_path = os.path.join(script_dir, 'produtos.json')

# Carregar lista inicial de produtos
produtos = load_produtos(produtos_file_path)

def criar_chaves_rsa():
    # Gera as chaves RSA

    global chave_privada, chave_publica

    chave_privada = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048
    )
    chave_publica = chave_privada.public_key()

    return chave_privada, chave_publica

def serializar_chave_publica(chave_publica):
    """Serializa a chave pública em formato PEM"""
    return chave_publica.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo
    ).decode('utf-8')

# Função para assinar a assinatura
def assinar_mensagem(message):
    if isinstance(message, (list, dict)):
        message_bytes = json.dumps(message, sort_keys=True).encode('utf-8')
    elif isinstance(message, str):
        message_bytes = message.encode('utf-8')
    else:
        raise TypeError("A mensagem deve ser uma string ou um objeto JSON serializável.")

    signature = chave_privada.sign(
        message_bytes,
        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
        hashes.SHA256()
    )

    # Decodificar usando 'cp437'
    try:
        return signature.decode('cp437')
    except UnicodeDecodeError as e:
        raise ValueError(f"Erro ao decodificar assinatura: {e}")


@app.route('/secure/categorias', methods=['GET'])
def listar_categorias_seguro():
    categorias = list(produtos.keys())

    resposta = {
        "assinatura": assinar_mensagem(categorias),
        "certificado": certificate.decode('utf-8'),
        "mensagem": categorias
    }

    return jsonify(resposta), 200

@app.route('/secure/produtos', methods=['GET'])
def listar_produtos_seguro():
    categoria = request.args.get("categoria")

    if categoria and categoria in produtos:
        # Extrair os produtos da categoria solicitada
        produtos_categoria = [
            {
                "categoria": categoria,
                "produto": item["nome"],
                "quantidade": item["quantidade"],
                "preco": item["preco"]
            }
            for item in produtos[categoria]
        ]

        # Montar a resposta
        resposta = {
            "assinatura": assinar_mensagem(produtos_categoria),
            "certificado": certificate.decode('utf-8'),
            "mensagem": produtos_categoria
        }

        return jsonify(resposta), 200

    # Caso a categoria não exista ou não seja especificada
    mensagem_erro = "Categoria inexistente ou não especificada"
    resposta = {
        "assinatura": assinar_mensagem(mensagem_erro),
        "certificado": certificate.decode('utf-8'),
        "mensagem": mensagem_erro
    }

    return jsonify(resposta), 404

# Rota para comprar uma quantidade de um produto específico
@app.route('/secure/comprar/<produto>/<int:quantidade>', methods=['POST'])
def comprar_produto_seguro(produto, quantidade):
    if quantidade <= 0:
        resposta = {
            "assinatura": assinar_mensagem("Quantidade inválida."),
            "certificado": certificate.decode('utf-8'),
            "mensagem": "Quantidade inválida."
        }
        return jsonify(resposta), 400

    for categoria, itens in produtos.items():
        # Buscar o produto dentro da lista de itens
        for item in itens:
            if item["nome"].lower() == produto.lower():  # Comparação case-insensitive
                # Verificar se há quantidade suficiente
                if item["quantidade"] >= quantidade:
                    item["quantidade"] -= quantidade

                    resposta = {
                        "assinatura": assinar_mensagem("Sucesso"),
                        "certificado": certificate.decode('utf-8'),
                        "mensagem": "Sucesso"
                    }
                    return jsonify(resposta), 200

                # Quantidade insuficiente
                resposta = {
                    "assinatura": assinar_mensagem("Quantidade indisponível"),
                    "certificado": certificate.decode('utf-8'),
                    "mensagem": "Quantidade indisponível"
                }
                return jsonify(resposta), 400

    # Produto não encontrado em nenhuma categoria
    resposta = {
        "assinatura": assinar_mensagem("Produto inexistente"),
        "certificado": certificate.decode('utf-8'),
        "mensagem": "Produto inexistente"
    }
    return jsonify(resposta), 404

def registrar_no_gestor_seguro(ip, porta, nome):
    """
    Registra o produtor no Gestor de Produtores com geração de chaves, assinatura da mensagem
    e obtenção do certificado digital.
    """
    global certificate
    # Gera as chaves RSA
    chave_privada, chave_publica = criar_chaves_rsa()

    chave_publica_pem = serializar_chave_publica(chave_publica)

    # URL e dados para registro
    url = "http://193.136.11.170:5001/produtor_certificado"
    data = {
        "ip": ip,
        "porta": porta,
        "nome": nome,
        "pubKey": chave_publica_pem
    }

    try:
        # Envia o registro ao Gestor
        response = requests.post(url, json=data)

        # Verifica a resposta do Gestor
        if response.status_code in [200, 201]:
            # Salva o certificado recebido
            certificate = response.text.encode('utf-8')
            print("Certificado obtido com sucesso")
            return True
        else:
            print(f"Erro ao registrar produtor: {response.status_code} - {response.text}")
            return False
    except Exception as e:
        print("Erro de conexão com o gestor:", e)
        return False

# Função para registar periodicamente o produtor REST a cada 5 minutos
def iniciar_registro_periodico_seguro(ip, porta, nome, intervalo=100):
    def registrar_periodicamente():
        while True:
            registrar_no_gestor_seguro(ip, porta, nome)
            time.sleep(intervalo)  # (100 segundos)

    # Iniciar o thread para registro periódico
    thread = threading.Thread(target=registrar_periodicamente, daemon=True)
    thread.start()


if __name__ == "__main__":
    # Argumentos de linha de comando para definir a porta
    parser = argparse.ArgumentParser(description='Start the producer server.')
    parser.add_argument('--port', type=int, default=5007, help='Port number to run the producer server on.')
    args = parser.parse_args()

    host = "localhost"
    port = args.port
    nome = "ProdREST oliv_seguro"

    # Converter 'localhost' para '127.0.0.1' para validação do IP
    ip = "127.0.0.1" if host == "localhost" else host

    # Registrar o produtor e iniciar o registro periódico
    registrar_no_gestor_seguro(ip, port, nome)
    iniciar_registro_periodico_seguro(ip, port, nome)

    # Iniciar o servidor Flask
    app.run(host=host, port=port, debug=True)
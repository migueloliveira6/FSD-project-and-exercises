import socket
import json
import threading
import time
from datetime import datetime
from idlelib.window import add_windows_to_menu
import requests
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives import hashes
from cryptography.x509 import load_pem_x509_certificate
from cryptography.hazmat.primitives.serialization import load_pem_public_key
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.backends import default_backend
from jinja2.filters import do_default
from cryptography.hazmat.primitives.asymmetric import rsa

produtores_rest = []
produtores = [
    {"ip": "localhost", "porta": 5004,
     "categorias": ["fruta", "livros", "roupa", "ferramentas", "computadores", "smartphones", "filmes", "sapatos",
                    "vegetais", "eletronicos"]},
    {"ip": "localhost", "porta": 5005,
     "categorias": ["fruta", "livros", "roupa", "ferramentas", "computadores", "smartphones", "filmes", "sapatos",
                    "vegetais", "eletronicos"]}
]

produtos_disponiveis = {}
categorias_por_produtor = {}
shopping_cart = []
lock = threading.Lock()

RESELL_MARKUP = 0.10

update_logs = []

# Segurança

from cryptography.x509 import load_pem_x509_certificate
from cryptography.hazmat.primitives.asymmetric import rsa


def validar_certificado(certificado_pem, public_key_gestor, nome_produtor, porta_produtor):
    try:
        # Garantir que o certificado inclua delimitadores corretamente
        certificado_pem = certificado_pem.strip()
        if not certificado_pem.startswith("-----BEGIN CERTIFICATE-----"):
            certificado_pem = "-----BEGIN CERTIFICATE-----\n" + certificado_pem
        if not certificado_pem.endswith("-----END CERTIFICATE-----"):
            certificado_pem = certificado_pem + "\n-----END CERTIFICATE-----"

        # Carregar o certificado PEM do produtor
        certificado = load_pem_x509_certificate(certificado_pem.encode('utf-8'))

        # Extrair a chave pública do certificado do produtor
        chave_publica_produtor = certificado.public_key()

        # Debugging para verificar o certificado e a chave pública
        print(f"Certificado para {nome_produtor} (IP: {nome_produtor}, Porta: {porta_produtor}): {certificado}")
        print(f"Chave pública do produtor: {chave_publica_produtor}")

        # Carregar e extrair a chave pública do gestor (expected key)
        public_key_gestor_obj = load_pem_x509_certificate(public_key_gestor.encode('utf-8')).public_key()

        # Comparar os números públicos das chaves RSA
        if isinstance(chave_publica_produtor, rsa.RSAPublicKey):
            if chave_publica_produtor.public_numbers() == public_key_gestor_obj.public_numbers():
                print(f"Certificado validado com sucesso para {nome_produtor} na porta {porta_produtor}.")
                return True
            else:
                print(f"Chave pública não corresponde ao esperado para {nome_produtor} na porta {porta_produtor}.")
                return False
        else:
            print(f"Tipo de chave pública inválido no certificado para {nome_produtor} na porta {porta_produtor}.")
            return False

    except Exception as e:
        print(f"Erro na validação do certificado para {nome_produtor} na porta {porta_produtor}: {e}")
        return False

def validar_resposta_rest(resposta, descricao_requisicao, nome_produtor, public_key_gestor, porta_produtor):
    """
    Valida a resposta recebida de um produtor REST seguro.
    """
    try:
        conteudo = resposta.json()
        campos_obrigatorios = ['assinatura', 'certificado', 'mensagem']

        if not all(campo in conteudo for campo in campos_obrigatorios):
            print(f"Resposta incompleta para {descricao_requisicao}.")
            return False

        assinatura = conteudo['assinatura']
        certificado_pem = conteudo['certificado']
        mensagem = conteudo['mensagem']

        if not validar_certificado(certificado_pem, public_key_gestor, nome_produtor, porta_produtor):
            return False

        if not validar_assinatura(assinatura, mensagem, certificado_pem, nome_produtor):
            return False

        return True

    except (json.JSONDecodeError, KeyError, TypeError) as e:
        print(f"Erro ao processar resposta REST para {nome_produtor}: {e}")
        return False

def listar_categorias_seguras(produtor):
    url = f"http://{produtor['ip']}:{produtor['porta']}/secure/categorias"
    try:
        resposta = requests.get(url, verify=True)
        if resposta.status_code == 200:
            conteudo = resposta.json()
            assinatura = conteudo['assinatura']
            certificado_pem = conteudo['certificado']
            mensagem = conteudo['mensagem']

            if validar_request(mensagem, assinatura, certificado_pem):
                # Exibição bonita das categorias
                print("\nCategorias disponíveis:")
                for index, categoria in enumerate(mensagem, start=1):
                    print(f"{index}. {categoria.capitalize()}")
                return mensagem
            else:
                print("Falha na validação da assinatura ou do certificado.")
                return None
        else:
            print(f"Erro ao listar categorias: {resposta.status_code}")
    except requests.RequestException as e:
        print(f"Erro ao conectar ao produtor {produtor['ip']}: {e}")
    return None


def listar_produtos_seguro(produtor, categoria):
    url = f"http://{produtor['ip']}:{produtor['porta']}/secure/produtos?categoria={categoria}"
    try:
        resposta = requests.get(url, verify=True)
        if resposta.status_code == 200:
            conteudo = resposta.json()
            assinatura = conteudo['assinatura']
            certificado_pem = conteudo['certificado']
            mensagem = conteudo['mensagem']

            if validar_request(mensagem, assinatura, certificado_pem):
                return mensagem
            return None
        elif resposta.status_code == 404:
            print(f"Erro: Categoria inexistente para o produtor {produtor['ip']}.")
        else:
            print(f"Erro ao listar produtos: {resposta.status_code}")
    except requests.RequestException as e:
        print(f"Erro ao conectar ao produtor {produtor['ip']}: {e}")
    return None


def buscar_categorias_e_produtos_seguro(produtor):
    produtos_disponiveis = {}

    categorias = listar_categorias_seguras(produtor)
    if categorias:
        for categoria in categorias:
            produtos = listar_produtos_seguro(produtor, categoria)
            if produtos:
                produtos_disponiveis.setdefault(categoria, []).extend(produtos)

    print("\nProdutos disponíveis:")
    for categoria, produtos in produtos_disponiveis.items():
        print(f"\nCategoria: {categoria.capitalize()}")
        for produto in produtos:
            print(f"  - Produto: {produto['produto']}")
            print(f"    Preço: {produto['preco']} €")
            print(f"    Quantidade: {produto['quantidade']}")

    return produtos_disponiveis

def comprar_produto_seguro(cliente_selecionado):
    # Exibir produtos disponíveis (chamando a função existente)
    print(f"Produtos disponíveis de {cliente_selecionado['nome']}:")
    categorias_produtos = buscar_categorias_e_produtos_seguro(cliente_selecionado)  # Função já existente no seu código

    # Criar uma lista com todos os produtos (independentemente da categoria)
    produtos_disponiveis = [
        produto
        for produtos_categoria in categorias_produtos.values()
        for produto in produtos_categoria
        if produto["quantidade"] > 0  # Apenas produtos com quantidade disponível
    ]

    # Exibir produtos com informações detalhadas
    for produto in produtos_disponiveis:
        print(f"Produto: {produto['produto']}, Categoria: {produto['categoria']}, Preço: €{produto['preco']}, Quantidade disponível: {produto['quantidade']}")

    # Seleção do produto pelo nome
    while True:
        nome_produto = input("Escolha um produto pelo nome: ").strip().lower()
        produto_selecionado = next((produto for produto in produtos_disponiveis if produto['produto'].lower() == nome_produto), None)

        if produto_selecionado:
            break
        else:
            print("Produto inválido ou indisponível. Por favor, tente novamente.")

    # Seleção da quantidade
    while True:
        try:
            quantidade = int(input(f"Digite a quantidade de {produto_selecionado['produto']} que deseja comprar: "))
            if 0 < quantidade <= produto_selecionado["quantidade"]:
                break
            else:
                print("Quantidade inválida. Certifique-se de que é maior que zero e não excede o disponível.")
        except ValueError:
            print("Entrada inválida. Por favor, insira um número.")

    # Enviar solicitação de compra
    url_compra = f"http://{cliente_selecionado['ip']}:{cliente_selecionado['porta']}/secure/comprar/{produto_selecionado['produto']}/{quantidade}"
    try:
        resposta = requests.post(url_compra, verify=True)
        if resposta.status_code == 200:
            conteudo = resposta.json()
            assinatura = conteudo['assinatura']
            certificado_pem = conteudo['certificado']
            mensagem = conteudo['mensagem']

            if validar_request(mensagem, assinatura, certificado_pem):
                return mensagem
            return None
        else:
            print(f"Erro na compra: {resposta.status_code} - {resposta.text}")
    except requests.RequestException as e:
        print(f"Erro ao conectar ao produtor para realizar a compra: {e}")


# -----------------------------------------------------------------------------------------------------------------------------------------------------

def conectar_produtor(host, port):
    cliente_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        cliente_socket.connect((host, port))
        update_logs.append(f"[{datetime.now()}] Conectado ao produtor em {host}:{port}")
        return cliente_socket
    except ConnectionRefusedError:
        update_logs.append(
            f"[{datetime.now()}] Erro: Não foi possível conectar ao produtor em {host}:{port}. ConnectionRefusedError")
        return None
    except Exception as e:
        update_logs.append(f"[{datetime.now()}] Erro inesperado ao conectar ao produtor em {host}:{port}: {e}")
        return None


def pedir_lista_produtos(cliente_socket, categorias):
    try:
        request = {
            "type": "listarProdutos",
            "categorias": categorias
        }
        cliente_socket.sendall(json.dumps(request).encode('utf-8'))
        resposta = cliente_socket.recv(4096).decode('utf-8')
        resposta_json = json.loads(resposta)
        return resposta_json
    except (ConnectionResetError, ConnectionAbortedError, ConnectionRefusedError, socket.error) as e:
        print(f"Erro ao pedir lista de produtos: {e}")
        return None
    except Exception as e:
        print(f"Erro ao pedir lista de produtos: {e}")
        return None


def atualizar_produtos():
    while True:
        for produtor in produtores:
            cliente_socket = conectar_produtor(produtor['ip'], produtor['porta'])
            if cliente_socket:
                try:
                    request = {
                        "type": "listarProdutos",
                        "categorias": produtor['categorias']
                    }
                    cliente_socket.sendall(json.dumps(request).encode('utf-8'))
                    resposta = cliente_socket.recv(4096).decode('utf-8')
                    produtos = json.loads(resposta)
                    if isinstance(produtos, dict):  # Verifica se é um dicionário
                        with lock:
                            for categoria, lista_produtos in produtos.items():
                                if isinstance(lista_produtos, list):  # Verifica se é uma lista
                                    for produto in lista_produtos:
                                        if isinstance(produto, dict):  # Verifica se o produto é um dicionário
                                            taxa_revenda = produto.get('taxa_revenda',
                                                                       0)  # Valor padrão caso não exista = 0
                                            produto['preco'] *= (1 + taxa_revenda)
                                    produtos_disponiveis[categoria] = lista_produtos
                                    update_logs.append(
                                        f"[{datetime.now()}] Produtos atualizados de {produtor['ip']}:{produtor['porta']} - Categoria: {categoria}")
                                    for produto in lista_produtos:
                                        update_logs.append(
                                            f"  - Produto: {produto['nome']}, Quantidade: {produto['quantidade']}, Preço: €{produto['preco']:.2f}")
                    else:
                        print(f"Erro: Resposta inesperada do servidor: {produtos}")
                except (ConnectionRefusedError, ConnectionResetError, socket.error) as e:
                    update_logs.append(
                        f"[{datetime.now()}] Erro ao conectar ao produtor {produtor['ip']}:{produtor['porta']}: {e}")
                except json.JSONDecodeError as e:
                    print(f"Erro ao decodificar a resposta JSON: {e}")
                finally:
                    cliente_socket.close()
            else:
                update_logs.append(
                    f"[{datetime.now()}] Tentativa de reconexão ao produtor {produtor['ip']}:{produtor['porta']} falhou.")
        time.sleep(60)  # Espera 60 segundos


def adicionar_ao_carrinho(categoria, produto, quantidade, cliente_selecionado):
    categoria = categoria.lower()  # Normaliza para minúsculas

    # Se a categoria não está carregada, procurar produtos automaticamente
    if categoria not in produtos_disponiveis:
        print(f"A carregar produtos para a categoria '{categoria}'...")

        if isinstance(cliente_selecionado, dict) and 'ip' in cliente_selecionado and 'porta' in cliente_selecionado:
            produtos = obter_lista_produtos_rest(cliente_selecionado['ip'], cliente_selecionado['porta'], [categoria])
        else:
            produtos = pedir_lista_produtos(cliente_selecionado, [categoria])

        with lock:
            for cat, lista_produtos in produtos.items():
                produtos_disponiveis[cat] = lista_produtos

        if categoria not in produtos_disponiveis:
            print(f"Erro: Categoria '{categoria}' não encontrada.")
            return

    # Verifica se o produto existe na categoria e processa a compra
    produto_encontrado = False
    for prod in produtos_disponiveis[categoria]:
        if prod['nome'].lower() == produto.lower():
            produto_encontrado = True
            if prod['quantidade'] < quantidade:
                print(f"Erro: Quantidade insuficiente de '{produto}'. Disponível: {prod['quantidade']}.")
                return

            taxa_revenda = prod.get('taxa_revenda', 0)  # Valor padrão xaso não exista
            preco_final_unidade = prod['preco'] * (1 + taxa_revenda)
            preco_total = preco_final_unidade * quantidade  # Multiplica pelo número de unidades

            # Check if the producer is a REST producer
            if isinstance(cliente_selecionado, dict) and 'ip' in cliente_selecionado and 'porta' in cliente_selecionado:
                compra_result = comprar_produto_rest(cliente_selecionado['ip'], cliente_selecionado['porta'], produto,
                                                     quantidade)
                if compra_result:
                    shopping_cart.append({
                        "categoria": categoria,
                        "produto": produto,
                        "quantidade": quantidade,
                        "preco": preco_total  # Preço total (por unidade * quantidade)
                    })
                    # Reduz a quantidade do produto disponível
                    with lock:
                        prod['quantidade'] -= quantidade
                    print(f"Produto '{produto}' adicionado ao carrinho. Preço total: €{preco_total:.2f}.")
                else:
                    print(f"Erro: Não foi possível comprar o produto '{produto}' do produtor REST.")
            else:
                # Gerir os produtores SOCKET
                request = {
                    "type": "comprar",
                    "categoria": categoria,
                    "produto": produto,
                    "quantidade": quantidade
                }
                cliente_selecionado.sendall(json.dumps(request).encode('utf-8'))
                resposta = cliente_selecionado.recv(1024).decode('utf-8')
                resposta_json = json.loads(resposta)

                if resposta_json.get("status") == "sucesso":
                    shopping_cart.append({
                        "categoria": categoria,
                        "produto": produto,
                        "quantidade": quantidade,
                        "preco": preco_total  # Preço total (por unidade * quantidade)
                    })
                    # Reduz a quantidade do produto disponível
                    with lock:
                        prod['quantidade'] -= quantidade
                    print(f"Produto '{produto}' adicionado ao carrinho. Preço total: €{preco_total:.2f}.")
                else:
                    print(f"Erro: {resposta_json.get('mensagem')}")
                return

    if not produto_encontrado:
        print(f"Erro: Produto '{produto}' não encontrado na categoria '{categoria}'.")


def listar_categorias(cliente_socket):
    try:
        request = {
            "type": "listarCategorias"
        }
        cliente_socket.sendall(json.dumps(request).encode('utf-8'))
        resposta = cliente_socket.recv(1024).decode('utf-8')
        resposta_json = json.loads(resposta)
        return resposta_json
    except Exception as e:
        print(f"Erro ao listar categorias: {e}")
        return []


def pedir_categorias(clientes_socket):
    global categorias_por_produtor
    categorias_por_produtor.clear()
    threads = []

    def listar_categorias_thread(cliente, produtor_index):
        if cliente is None:
            print(f"Erro: Socket do produtor {produtor_index + 1} é None.")
            return
        try:
            categorias = listar_categorias(cliente, produtor_index)
            if categorias:
                categorias_por_produtor[produtor_index] = categorias
            else:
                print(f"Produtor {produtor_index + 1} não retornou categorias.")
        except ConnectionError as e:
            update_logs.append(f"Erro ao listar categorias do produtor {produtor_index + 1}: {e}")
        except Exception as e:
            update_logs.append(f"Erro inesperado ao listar categorias do produtor {produtor_index + 1}: {e}")

    # Criar e iniciar threads para cada cliente
    for index, cliente in enumerate(clientes_socket):
        thread = threading.Thread(target=listar_categorias_thread, args=(cliente, index))
        threads.append(thread)
        thread.start()

    # Aguardar todas as threads concluírem
    for thread in threads:
        thread.join()

    # Exibir categorias disponíveis por produtor
    print("\n=== Categorias Disponíveis por Produtor ===")
    print("=" * 40)

    if not categorias_por_produtor:
        print("Nenhuma categoria disponível para os produtores conectados.")
    else:
        for produtor_index, categorias in categorias_por_produtor.items():
            print(f"Produtor {produtor_index + 1}:")
            for i, categoria in enumerate(categorias, 1):
                print(f"  {i}. {categoria.capitalize()}")

    print("=" * 40)


def exibir_produtos_disponiveis(produtor):
    produtos = listar_produtos_seguro(produtor, categorias)
    categorias1 = listar_categorias_seguras(produtor)
    if not produtos:
        print("\nNenhum produto encontrado para as categorias especificadas.")
        return

    print("\n=== Produtos Disponíveis por Categoria ===")
    for categorias1, lista_produtos in produtos.items():
        print(f"\nCategoria: {categoria.capitalize()}")
        print("=" * 30)
        for produto in lista_produtos:
            nome = produto.get('produto', 'Desconhecido')
            preco = produto.get('preco', 'Indisponível')
            quantidade = produto.get('quantidade', 'Indisponível')
            print(f"  - {nome} | Preço: {preco} | Quantidade: {quantidade}")


def exibir_atualizacoes():
    print("\n=== Atualizações Recentes ===")
    for log in update_logs:
        print(log)
    print("=============================")


def exibir_carrinho():
    if not shopping_cart:
        print("\nCarrinho está vazio.")
        return

    print("\n=== Carrinho de Compras ===")
    for item in shopping_cart:
        print(
            f"Produto: {item['produto']}, Categoria: {item['categoria']}, Quantidade: {item['quantidade']}, Preço: €{item['preco']:.2f}")
    print("===========================")


def exibir_lucro():
    lucro_total = 0  # Variável para armazenar o lucro total

    for item in shopping_cart:

        for prod in produtos_disponiveis[item['categoria']]:
            if prod['nome'].lower() == item['produto'].lower():
                # Calcula o lucro com base na taxa de revenda
                preco_original = prod['preco']
                taxa_revenda = prod['taxa_revenda']
                quantidade_comprada = item['quantidade']

                # O lucro é o valor da taxa de revenda multiplicado pelo preço original e pela quantidade
                lucro_por_produto = (preco_original * taxa_revenda) * quantidade_comprada
                lucro_total += lucro_por_produto
                break

    print(f"Lucro total obtido com as vendas: €{lucro_total:.2f}")


# FUNÇÕES REST

def obter_lista_produtos_rest(host, port, categorias):
    produtos_por_categoria = {}
    for categoria in categorias:
        url = f"http://{host}:{port}/secure/categorias"

        try:
            response = requests.get(url)
            if response.status_code == 200:
                produtos = response.json()
                for produto in produtos:
                    taxa_revenda = produto.get('taxa_revenda', 0)  # Valor padrão = 0
                    produto['preco'] *= (1 + taxa_revenda)  # Aplica a taxa
                produtos_por_categoria[categoria] = produtos
                update_logs.append(f"[{datetime.now()}] Produtos obtidos de {host}:{port} para a categoria {categoria}")
            else:
                update_logs.append(
                    f"[{datetime.now()}] Erro ao obter produtos de {host}:{port} para a categoria {categoria}: {response.status_code}")
                produtos_por_categoria[categoria] = []
        except requests.ConnectionError:
            update_logs.append(f"[{datetime.now()}] Erro: Não foi possível conectar ao produtor REST em {host}:{port}.")
            produtos_por_categoria[categoria] = []
        except Exception as e:
            update_logs.append(f"[{datetime.now()}] Erro inesperado ao obter produtos de {host}:{port}: {e}")
            produtos_por_categoria[categoria] = []
    return produtos_por_categoria


def comprar_produto_rest(host, port, produto_nome):
    url = f"http://{host}:{port}/secure/categorias"

    try:
        response = requests.get(url)
        if response.status_code == 200:
            update_logs.append(
                f"[{datetime.now()}] Compra realizada com sucesso de {host}:{port} para o produto {produto_nome}")
            return response.json()
        else:
            update_logs.append(
                f"[{datetime.now()}] Erro ao comprar produto de {host}:{port}: {response.status_code} - {response.text}")
            print(
                f"Erro ao comprar produto de {host}:{port}: {response.status_code} - {response.text}")  # Debug
            return None
    except requests.ConnectionError as e:
        update_logs.append(f"[{datetime.now()}] Erro: Não foi possível conectar ao produtor REST em {host}:{port}. {e}")
        print(f"Erro: Não foi possível conectar ao produtor REST em {host}:{port}. {e}")  # Debug
        return None
    except Exception as e:
        update_logs.append(f"[{datetime.now()}] Erro inesperado ao comprar produto de {host}:{port}: {e}")
        print(f"Erro inesperado ao comprar produto de {host}:{port}: {e}")  # Debug
        return None


def listar_categorias_rest(host, port):
    """
    Lista as categorias oferecidas por um produtor REST específico.
    """
    url = f"http://{host}:{port}/secure/categorias"

    try:
        response = requests.get(url)
        if response.status_code == 200:
            return response.json()
        else:
            update_logs.append(f"[{datetime.now()}] Erro ao obter categorias de {host}:{port}: {response.status_code}")
            return []
    except requests.ConnectionError:
        update_logs.append(f"[{datetime.now()}] Erro: Não foi possível conectar ao produtor REST em {host}:{port}.")
        return []
    except Exception as e:
        update_logs.append(f"[{datetime.now()}] Erro inesperado ao obter categorias de {host}:{port}: {e}")
        return []


def obter_lista_produtores_rest():
    url = "http://193.136.11.170:5001/produtor"
    try:
        response = requests.get(url)
        if response.status_code == 200:
            produtores = response.json()
            update_logs.append(f"[{datetime.now()}] Produtores obtidos do Gestor de Produtores: {produtores}")
            print(f"Produtores obtidos do Gestor de Produtores: {produtores}")  # Debug
            return produtores
        else:
            update_logs.append(
                f"[{datetime.now()}] Erro ao obter produtores do Gestor de Produtores: {response.status_code}")
            print(f"Erro ao obter produtores do Gestor de Produtores: {response.status_code}")  # Debug
            return []
    except requests.ConnectionError:
        update_logs.append(f"[{datetime.now()}] Erro: Não foi possível conectar ao Gestor de Produtores.")
        print("Erro: Não foi possível conectar ao Gestor de Produtores.")  # Debug
        return []
    except Exception as e:
        update_logs.append(f"[{datetime.now()}] Erro inesperado ao obter produtores do Gestor de Produtores: {e}")
        print(f"Erro inesperado ao obter produtores do Gestor de Produtores: {e}")  # Debug
        return []


def obter_lista_produtores_rest_seguro():
    url = "http://193.136.11.170:5001/produtor"
    try:
        response = requests.get(url, verify=True)  # Set verify to True to verify SSL certificates
        if response.status_code == 200:
            produtores = response.json()
            secure_produtores = [produtor for produtor in produtores if produtor.get('secure') == 1]
            update_logs.append(
                f"[{datetime.now()}] Produtores seguros obtidos do Gestor de Produtores: {secure_produtores}")
            print(f"Produtores seguros obtidos do Gestor de Produtores: {secure_produtores}")  # Debug
            return secure_produtores
        else:
            update_logs.append(
                f"[{datetime.now()}] Erro ao obter produtores do Gestor de Produtores Seguro: {response.status_code}")
            print(f"Erro ao obter produtores do Gestor de Produtores Seguro: {response.status_code}")  # Debug
            return []
    except requests.ConnectionError:
        update_logs.append(f"[{datetime.now()}] Erro: Não foi possível conectar ao Gestor de Produtores Seguro.")
        print("Erro: Não foi possível conectar ao Gestor de Produtores Seguro.")  # Debug
        return []
    except Exception as e:
        update_logs.append(
            f"[{datetime.now()}] Erro inesperado ao obter produtores do Gestor de Produtores Seguro: {e}")
        print(f"Erro inesperado ao obter produtores do Gestor de Produtores Seguro: {e}")  # Debug
        return []


def obter_lista_produtores_categorias_rest(categorias_subscritas):
    """
    Obtém a lista de produtores REST do Gestor de Produtores e filtra para incluir
    apenas aqueles que oferecem as categorias subscritas pelo Marketplace.
    """
    url = "http://193.136.11.170:5001/produtor"
    try:
        response = requests.get(url)
        if response.status_code != 200:
            update_logs.append(f"[{datetime.now()}] Erro ao obter produtores: {response.status_code}")
            print(f"Erro ao obter produtores do Gestor: {response.status_code}")
            return []

        produtores_data = response.json()
        produtores_filtrados = []

        for produtor in produtores_data:
            nome = produtor.get("nome")
            ip = produtor.get("ip")
            porta = produtor.get("porta")
            secure = produtor.get("secure")

            if secure == 1:
                categorias = listar_categorias_seguras({"ip": ip, "porta": porta})
            else:
                categorias = listar_categorias_rest(ip, porta)

            if categorias and any(categoria in categorias for categoria in categorias_subscritas):
                produtores_filtrados.append({
                    "nome": nome,
                    "categorias": categorias
                })

        update_logs.append(f"[{datetime.now()}] Produtores filtrados: {produtores_filtrados}")
        return produtores_filtrados

    except requests.ConnectionError:
        update_logs.append(f"[{datetime.now()}] Erro: Não foi possível conectar ao Gestor de Produtores.")
        print("Erro: Não foi possível conectar ao Gestor de Produtores.")
        return []

    except Exception as e:
        update_logs.append(f"[{datetime.now()}] Erro inesperado ao obter produtores: {e}")
        print(f"Erro inesperado ao obter produtores: {e}")
        return []


def validar_request(mensagem, assinatura, certificado_pem):
    certificado = load_pem_x509_certificate(certificado_pem.encode("utf-8"))
    public_key = certificado.public_key()

    if (isinstance(mensagem, str)):
        mensagem_decoded = mensagem.encode("utf-8")
    else:
        mensagem_decoded = json.dumps(mensagem).encode('utf-8')

    assinatura_decoded = assinatura.encode("cp437")
    # Abrir Manager Pem
    try:
        with open("./manager_public_key.pem", "rb") as key_file:
            manager_public_key = load_pem_public_key(key_file.read())
    except Exception as e:
        print(e)

    # Validar Certificado
    try:
        manager_public_key.verify(
            certificado.signature,
            certificado.tbs_certificate_bytes,
            padding.PKCS1v15(),
            hashes.SHA256()
        )
    except Exception as e:
        print(f"Erro ao validar Certificado | {e}")
        return False

    # Validar Assinatura
    try:
        public_key.verify(
            assinatura_decoded,
            mensagem_decoded,
            padding.PSS(
                mgf=padding.MGF1(hashes.SHA256()),
                salt_length=padding.PSS.MAX_LENGTH
            ),
            hashes.SHA256()
        )
        return True
    except Exception as e:
        print(f"Erro ao validar Assinatura | {e}")
        return False

def iniciar_marketplace():
    global produtores_rest
    categorias_subscritas = ["fruta"]

    produtores_rest = obter_lista_produtores_rest()
    produtores_seguro = obter_lista_produtores_rest_seguro()
    print(f"Produtores REST obtidos: {produtores_rest}")
    print(f"Produtores REST Seguro obtidos: {produtores_seguro}")

    #produtores_categorias_subs = obter_lista_produtores_categorias_rest(categorias_subscritas)
    #print(f"Produtores REST obtidos com as categorias subscritas: {produtores_categorias_subs}\n")
    #print(f"Categorias subscritas pelo Marketplace: {categorias_subscritas}")

    all_produtores = produtores_rest

    def selecionar_produtor():
        print("\n=== Produtores Disponíveis ===")
        for i, produtor in enumerate(all_produtores, 1):
            if 'ip' in produtor and 'porta' in produtor:
                tipo = "Seguro" if produtor.get("secure", False) else "REST"
                print(f"{i}. {produtor['ip']}:{produtor['porta']} - {produtor['nome']} ({tipo})")
            else:
                print(f"{i}. {produtor['ip']}:{produtor['porta']} (Socket)")

        try:
            produtor_index = int(input("Selecione um produtor pelo número: ")) - 1
            if produtor_index < 0 or produtor_index >= len(all_produtores):
                print("Erro: Produtor inválido.")
                return None, None, None

            cliente_selecionado = all_produtores[produtor_index]
            is_rest_producer = 'ip' in cliente_selecionado and 'porta' in cliente_selecionado
            is_secure_producer = cliente_selecionado.get("secure", False)

            if is_rest_producer:
                tipo = "REST Seguro" if is_secure_producer else "REST"
                print(f"Produtor {tipo} selecionado: {cliente_selecionado['ip']}:{cliente_selecionado['porta']}")
            else:
                print(f"Produtor Socket selecionado: {cliente_selecionado['ip']}:{cliente_selecionado['porta']}")
                cliente_socket = conectar_produtor(cliente_selecionado['ip'], cliente_selecionado['porta'])
                if not cliente_socket:
                    print(
                        f"Erro: Não foi possível conectar ao produtor socket {cliente_selecionado['ip']}:{cliente_selecionado['porta']}")
                    return None, None, None
                cliente_selecionado = cliente_socket

            return cliente_selecionado, is_rest_producer, is_secure_producer

        except ValueError:
            print("Erro: Entrada inválida. Por favor, insira um número válido.")
            return None, None, None

    cliente_selecionado, is_rest_producer, is_secure_producer = selecionar_produtor()

    if cliente_selecionado is None:
        return

    # Inicia thread de atualizações para produtores não seguros
    if not is_secure_producer:
        update_thread = threading.Thread(target=atualizar_produtos, daemon=True)
        update_thread.start()

    while True:
        print("\nEscolha uma ação:")
        print("1. Desconectar e Reconectar")
        print("2. Listar categorias seguros")
        print("3. Listar produtos seguros")
        print("4. Comprar produto seguro")
        print("5. Sair")
        option = input("Opção: ")

        if option == "1":
            print("A desconectar do produtor.")
            cliente_selecionado = None

            cliente_selecionado, is_rest_producer, is_secure_producer = selecionar_produtor()
            if cliente_selecionado is None:
                return

        elif option == "2":
            listar_categorias_seguras(cliente_selecionado)

        elif option == "3":
            buscar_categorias_e_produtos_seguro(cliente_selecionado)

        elif option == "4":
            compra = comprar_produto_seguro(cliente_selecionado)
            print(compra)

        elif option == "5":
            print("A sair do Marketplace.")
            break
        else:
            print("Erro: Opção inválida.")

if __name__ == "__main__":
    iniciar_marketplace()
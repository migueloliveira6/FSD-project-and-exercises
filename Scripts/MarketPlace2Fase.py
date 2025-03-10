import socket
import json
import threading
import time
from datetime import datetime
import requests

produtores_rest = []
produtores = [
    {"host": "10.8.0.3", "port": 5004,
     "categorias": ["fruta", "livros", "roupa", "ferramentas", "computadores", "smartphones", "filmes", "sapatos",
                    "vegetais", "eletronicos"]},
    {"host": "10.8.0.3", "port": 5005,
     "categorias": ["fruta", "livros", "roupa", "ferramentas", "computadores", "smartphones", "filmes", "sapatos",
                    "vegetais", "eletronicos"]}
]

produtos_disponiveis = {}
categorias_por_produtor = {}
shopping_cart = []
lock = threading.Lock()

RESELL_MARKUP = 0.10

update_logs = []


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
            cliente_socket = conectar_produtor(produtor['host'], produtor['port'])
            if cliente_socket:
                try:
                    request = {
                        "type": "listarProdutos",
                        "categorias": produtor['categorias']
                    }
                    cliente_socket.sendall(json.dumps(request).encode('utf-8'))
                    resposta = cliente_socket.recv(4096).decode('utf-8')
                    produtos = json.loads(resposta)
                    if isinstance(produtos, dict):  # Ensure produtos is a dictionary
                        with lock:
                            for categoria, lista_produtos in produtos.items():
                                if isinstance(lista_produtos, list):  # Ensure lista_produtos is a list
                                    for produto in lista_produtos:
                                        if isinstance(produto, dict):  # Ensure produto is a dictionary
                                            taxa_revenda = produto.get('taxa_revenda',
                                                                       0)  # Provide default value if missing
                                            produto['preco'] *= (1 + taxa_revenda)
                                    produtos_disponiveis[categoria] = lista_produtos
                                    update_logs.append(
                                        f"[{datetime.now()}] Produtos atualizados de {produtor['host']}:{produtor['port']} - Categoria: {categoria}")
                                    for produto in lista_produtos:
                                        update_logs.append(
                                            f"  - Produto: {produto['nome']}, Quantidade: {produto['quantidade']}, Preço: €{produto['preco']:.2f}")
                    else:
                        print(f"Erro: Resposta inesperada do servidor: {produtos}")
                except (ConnectionRefusedError, ConnectionResetError, socket.error) as e:
                    update_logs.append(
                        f"[{datetime.now()}] Erro ao conectar ao produtor {produtor['host']}:{produtor['port']}: {e}")
                except json.JSONDecodeError as e:
                    print(f"Erro ao decodificar a resposta JSON: {e}")
                finally:
                    cliente_socket.close()
            else:
                update_logs.append(
                    f"[{datetime.now()}] Tentativa de reconexão ao produtor {produtor['host']}:{produtor['port']} falhou.")
        time.sleep(60)  # Wait for 60 seconds before the next update


def adicionar_ao_carrinho(categoria, produto, quantidade, cliente_selecionado):
    categoria = categoria.lower()  # Normaliza para minúsculas

    # Se a categoria não está carregada, buscar produtos automaticamente
    if categoria not in produtos_disponiveis:
        print(f"Carregando produtos para a categoria '{categoria}'...")

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

            taxa_revenda = prod.get('taxa_revenda', 0)  # Provide default value if missing
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
                # Handle socket-based producers
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
    categorias_por_produtor.clear()
    threads = []

    def listar_categorias_thread(cliente, produtor_index):
        if cliente is None:
            print(f"Erro: Socket do produtor {produtor_index + 1} é None.")
            return
        try:
            categorias = listar_categorias(cliente, produtor_index)
            categorias_por_produtor[produtor_index] = categorias
        except ConnectionError as e:
            update_logs.append(f"Erro ao listar categorias do produtor {produtor_index + 1}: {e}")
        except Exception as e:
            update_logs.append(f"Erro inesperado ao listar categorias do produtor {produtor_index + 1}: {e}")

    for index, cliente in enumerate(clientes_socket):
        thread = threading.Thread(target=listar_categorias_thread, args=(cliente, index))
        threads.append(thread)
        thread.start()

    for thread in threads:
        thread.join()

    print("\n=== Categorias Disponíveis por Produtor ===")
    print("=" * 40)

    for produtor_index, categorias in categorias_por_produtor.items():
        print(f"Produtor {produtor_index + 1}:")
        for i, categoria in enumerate(categorias, 1):
            print(f"  {i}. {categoria.capitalize()}")

    print("=" * 40)


def exibir_produtos_disponiveis(categorias):
    produtos_exibidos = False

    for categoria in categorias:
        if categoria in produtos_disponiveis:
            if not produtos_exibidos:
                print("\n=== Produtos Disponíveis por Categoria ===")
                produtos_exibidos = True

            print(f"\nCategoria: {categoria.capitalize()}")
            print("=" * (len(categoria) + 11))
            for produto in produtos_disponiveis[categoria]:
                nome = produto['nome']
                quantidade = produto['quantidade']
                preco = produto['preco']
                print(f" - Produto: {nome.capitalize()}, Quantidade: {quantidade}, Preço: €{preco:.2f}")
        else:
            print(f"Erro: Categoria '{categoria}' não encontrada.")


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
        url = f"http://{host}:{port}/produtos?categoria={categoria}"
        try:
            response = requests.get(url)
            if response.status_code == 200:
                produtos = response.json()
                for produto in produtos:
                    taxa_revenda = produto.get('taxa_revenda', 0)  # Provide default value if missing
                    produto['preco'] *= (1 + taxa_revenda)  # Apply markup
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


def comprar_produto_rest(host, port, produto_nome, quantidade):
    url = f"http://{host}:{port}/comprar/{produto_nome}/{quantidade}"
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
                f"Erro ao comprar produto de {host}:{port}: {response.status_code} - {response.text}")  # Debug statement
            return None
    except requests.ConnectionError as e:
        update_logs.append(f"[{datetime.now()}] Erro: Não foi possível conectar ao produtor REST em {host}:{port}. {e}")
        print(f"Erro: Não foi possível conectar ao produtor REST em {host}:{port}. {e}")  # Debug statement
        return None
    except Exception as e:
        update_logs.append(f"[{datetime.now()}] Erro inesperado ao comprar produto de {host}:{port}: {e}")
        print(f"Erro inesperado ao comprar produto de {host}:{port}: {e}")  # Debug statement
        return None


def listar_categorias_rest(host, port):
    """
    Lista as categorias oferecidas por um produtor REST específico.
    """
    url = f"http://{host}:{port}/categorias"
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
            print(f"Produtores obtidos do Gestor de Produtores: {produtores}")  # Debug statement
            return produtores
        else:
            update_logs.append(
                f"[{datetime.now()}] Erro ao obter produtores do Gestor de Produtores: {response.status_code}")
            print(f"Erro ao obter produtores do Gestor de Produtores: {response.status_code}")  # Debug statement
            return []
    except requests.ConnectionError:
        update_logs.append(f"[{datetime.now()}] Erro: Não foi possível conectar ao Gestor de Produtores.")
        print("Erro: Não foi possível conectar ao Gestor de Produtores.")  # Debug statement
        return []
    except Exception as e:
        update_logs.append(f"[{datetime.now()}] Erro inesperado ao obter produtores do Gestor de Produtores: {e}")
        print(f"Erro inesperado ao obter produtores do Gestor de Produtores: {e}")  # Debug statement
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
        produtores_filtrados = [
            {
                "nome": produtor.get("nome"),
                "categorias": listar_categorias_rest(produtor.get("ip"), produtor.get("porta"))
            }
            for produtor in produtores_data
            if any(categoria in listar_categorias_rest(produtor.get("ip"), produtor.get("porta"))
                   for categoria in categorias_subscritas)
        ]

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


def iniciar_marketplace():
    global produtores_rest, produtores_categorias_subs
    categorias_subscritas = ["fruta"]
    produtores_rest = obter_lista_produtores_rest()
    print(f"Produtores REST obtidos: {produtores_rest}")  # Debug statement

    #produtores_categorias_subs = obter_lista_produtores_categorias_rest(categorias_subscritas)
    #print(f"Produtores REST obtidos com as categorias subscritas: {produtores_categorias_subs}\n")
    #print(f"Categorias subscritas pelo Marketplace: {categorias_subscritas}")

    # Combine both REST and socket-based producers for selection
    all_produtores = produtores + produtores_rest

    def selecionar_produtor():
        print("\n=== Produtores Disponíveis ===")
        for i, produtor in enumerate(all_produtores, 1):
            if 'ip' in produtor and 'porta' in produtor:
                print(f"{i}. {produtor['ip']}:{produtor['porta']} - {produtor['nome']}")
            else:
                print(f"{i}. {produtor['host']}:{produtor['port']}")

        produtor_index = int(input("Selecione um produtor pelo número: ")) - 1
        if produtor_index < 0 or produtor_index >= len(all_produtores):
            print("Erro: Produtor inválido.")
            return None, None

        cliente_selecionado = all_produtores[produtor_index]
        is_rest_producer = 'ip' in cliente_selecionado and 'porta' in cliente_selecionado

        if is_rest_producer:
            print(
                f"Produtor REST {produtor_index + 1} selecionado: {cliente_selecionado['ip']}:{cliente_selecionado['porta']}")
        else:
            print(
                f"Produtor Socket {produtor_index + 1} selecionado: {cliente_selecionado['host']}:{cliente_selecionado['port']}")
            cliente_socket = conectar_produtor(cliente_selecionado['host'], cliente_selecionado['port'])
            if not cliente_socket:
                print(
                    f"Erro: Não foi possível conectar ao produtor socket {cliente_selecionado['host']}:{cliente_selecionado['port']}")
                return None, None
            cliente_selecionado = cliente_socket

        return cliente_selecionado, is_rest_producer

    cliente_selecionado, is_rest_producer = selecionar_produtor()
    if cliente_selecionado is None:
        return

    update_thread = threading.Thread(target=atualizar_produtos, daemon=True)
    update_thread.start()

    while True:
        print("\nEscolha uma ação:")
        print("1. Listar produtos")
        print("2. Adicionar produto ao carrinho")
        print("3. Solicitar categorias")
        print("4. Ver atualizações")
        print("5. Ver carrinho")
        print("6. Ver Lucro")
        print("7. Desconectar e Reconectar")
        print("8. Sair")
        option = input("Opção: ")

        if option == "1":
            categorias_input = input("Digite as categorias separadas por vírgulas: ").strip()

            if not categorias_input:
                print("\nErro: Nenhuma categoria foi inserida. Tente novamente.")
                continue

            categorias = [cat.strip().lower() for cat in categorias_input.split(",")]

            if is_rest_producer:
                produtos = obter_lista_produtos_rest(cliente_selecionado['ip'], cliente_selecionado['porta'],
                                                     categorias)
            else:
                produtos = pedir_lista_produtos(cliente_selecionado, categorias)

            if produtos is None:
                print("Erro: Não foi possível obter a lista de produtos. Tentando conectar a outro produtor.")
                cliente_selecionado, is_rest_producer = selecionar_produtor()
                if cliente_selecionado is None:
                    return
                continue

            with lock:
                for categoria, lista_produtos in produtos.items():
                    produtos_disponiveis[categoria] = lista_produtos
            exibir_produtos_disponiveis(categorias)

        elif option == "2":
            categoria = input("Categoria do produto: ")
            produto = input("Nome do produto: ")
            try:
                quantidade = int(input("Quantidade a comprar: "))
            except ValueError:
                print("Erro: Quantidade inválida. Digite um número.")
                continue
            adicionar_ao_carrinho(categoria, produto, quantidade, cliente_selecionado)

        elif option == "3":
            if is_rest_producer:
                categorias = listar_categorias_rest(cliente_selecionado['ip'], cliente_selecionado['porta'])
            else:
                categorias = listar_categorias(cliente_selecionado)
            print(f"Categorias do produtor: {categorias}")

        elif option == "4":
            exibir_atualizacoes()
            if is_rest_producer:
                categorias = listar_categorias_rest(cliente_selecionado['ip'], cliente_selecionado['porta'])
                print(f"Categorias do produtor: {categorias}")

        elif option == "5":
            exibir_carrinho()

        elif option == "6":
            exibir_lucro()

        elif option == "7":
            print("Desconectando do produtor.")
            cliente_selecionado = None

            cliente_selecionado, is_rest_producer = selecionar_produtor()
            if cliente_selecionado is None:
                return

        elif option == "8":
            print("A sair do Marketplace.")
            break

        else:
            print("Erro: Opção inválida.")


if __name__ == "__main__":
    iniciar_marketplace()
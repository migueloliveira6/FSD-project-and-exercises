import socket
import threading
import json
import time
import requests

from cryptography.x509 import load_pem_x509_certificate
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric import padding  # Importe o padding aqui
from cryptography.exceptions import InvalidSignature


class Marketplace:
    def __init__(self, manager_url="http://193.136.11.170:5001"):
        self.products = {}
        self.lock = threading.Lock()
        self.manager_url = manager_url

    def get_producers_from_config(self, config_file):
        try:
            with open(config_file, "r") as f:
                producers_config = json.load(f)
                return [
                    {"producer_ip": p["ip"], "producer_port": p["porta"]} for p in producers_config
                ]
        except (FileNotFoundError, json.JSONDecodeError, KeyError) as e:
            print(f"Erro ao ler ou analisar o arquivo de configuração")
            return []

    def fetch_products(self, producer_ip, producer_port):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.connect((producer_ip, producer_port))
                request = {"tipo": "lista_produtos"}
                s.sendall(json.dumps(request).encode('utf-8'))
                response_data = s.recv(4096)
                if not response_data:
                    print(f"Resposta vazia de {producer_ip}:{producer_port}")
                    return []
                products = json.loads(response_data.decode('utf-8'))
                return products

        except (socket.timeout, ConnectionRefusedError, OSError, json.JSONDecodeError) as e:
            print(f"Erro ao conectar ou receber dados de {producer_ip}:{producer_port}")
            return []

    def get_rest_producers(self):
        try:
            response = requests.get(f"{self.manager_url}/produtor")
            response.raise_for_status()
            producers = response.json()
            return producers
        except requests.exceptions.RequestException as e:
            print(f"Erro ao obter produtores REST")
            return []

    def fetch_rest_products(self, producer):
        try:
            base_url = f"http://{producer['ip']}:{producer['porta']}"

            categories_response = requests.get(f"{base_url}/categorias")
            categories_response.raise_for_status()
            categories = categories_response.json()

            all_products = []
            for category in categories:
                products_response = requests.get(f"{base_url}/produtos", params={"categoria": category})
                products_response.raise_for_status()
                products = products_response.json()
                all_products.extend(products)

            return all_products

        except requests.exceptions.RequestException as e:
            print(f"Erro ao obter produtos REST de {producer['nome']}")
            return []

    def update_products(self, file_producers):
        with self.lock:
            self.products = {}

            for producer in file_producers:
                fetched_products = self.fetch_products(producer['producer_ip'], producer['producer_port'])
                if fetched_products:
                    for product in fetched_products:
                        product['preco'] = round(product['preco'], 2)
                        product['preco'] = f"{product['preco']}€"
                    self.products[f"{producer['producer_ip']}:{producer['producer_port']}"] = fetched_products

            rest_producers = self.get_rest_producers()
            for producer in rest_producers:
                fetched_products = self.fetch_rest_products(producer)
                if fetched_products:
                    for product in fetched_products:
                        product['preco'] = round(product['preco'], 2)
                        product['preco'] = f"{product['preco']}€"
                    self.products[f"{producer['ip']}:{producer['porta']}"] = fetched_products

    def buy_product(self, producer_address, product_name, quantity):
        producer_ip, producer_port = producer_address.split(":")
        producer_port = int(producer_port)

        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.connect((producer_ip, producer_port))
                request = {
                    "tipo": "compra_produto",
                    "produto": product_name,
                    "quantidade": quantity
                }
                s.sendall(json.dumps(request).encode('utf-8'))

                response_data = s.recv(4096)
                if not response_data:
                    print(f"Nenhuma resposta recebida de {producer_ip}:{producer_port} após a tentativa de compra.")
                    return
                response = json.loads(response_data.decode('utf-8'))
                print(response.get('mensagem', 'Resposta do servidor desconhecida'))

        except Exception as e:
            print(f"Erro durante a compra de {producer_ip}:{producer_port}")

    def buy_rest_product(self, producer_ip, producer_port, product_name, quantity):
        try:
            base_url = f"http://{producer_ip}:{producer_port}"
            response = requests.get(f"{base_url}/comprar/{product_name}/{quantity}")
            if response.status_code == 200:
                print(response.text)
            else:
                print("Erro a realizar a compra!")

        except requests.exceptions.RequestException as e:
            print(f"Erro ao comprar produto REST de {producer_ip}:{producer_port}")

    def validate_certificate(self, certificate_pem, gestor_public_key_pem, producer_name):
        try:
            certificate = load_pem_x509_certificate(certificate_pem, default_backend())
            gestor_pkey = serialization.load_pem_public_key(
                gestor_public_key_pem.encode('utf-8'), backend=default_backend()
            )
            gestor_pkey.verify(
                certificate.signature,
                certificate.tbs_certificate_bytes,
                padding.PKCS1v15(),
                certificate.signature_hash_algorithm,
            )
            return True
        except InvalidSignature:
            print(f"Certificado inválido para o produtor {producer_name}")
            return False
        except Exception as e:
            print(f"Erro ao processar o certificado: {producer_name}")
            return False

    def validate_signature(self, signature, message, certificate_pem, producer_name):
        signature = signature.encode("cp437")
        message_bytes = json.dumps(message).encode('utf-8')
        certificate = load_pem_x509_certificate(certificate_pem, default_backend())
        public_key = certificate.public_key()
        try:
            public_key.verify(
                signature,
                message_bytes,
                padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
                hashes.SHA256()
            )
            return True
        except InvalidSignature:
            print(f"Assinatura inválida para o produtor {producer_name}")
            return False

    def fetch_secure_rest_products(self):
        all_secure_products = {}
        rest_producers = self.get_rest_producers()

        for producer in rest_producers:
            try:
                base_url = f"http://{producer['ip']}:{producer['porta']}"

                categories_response = requests.get(f"{base_url}/secure/categorias")
                categories_response.raise_for_status()
                if not self.validate_rest_response(categories_response, f"categorias de {producer['nome']}",
                                                   producer['nome']):
                    continue

                categories = categories_response.json()['mensagem']

                producer_products = []
                for category in categories:

                    products_response = requests.get(f"{base_url}/secure/produtos", params={"categoria": category})
                    products_response.raise_for_status()
                    if not self.validate_rest_response(products_response,
                                                       f"produtos da categoria {category} de {producer['nome']}",
                                                       producer['nome']):
                        continue

                    products = products_response.json()['mensagem']
                    producer_products.extend(products)

                if producer_products:
                    all_secure_products[producer['nome']] = producer_products

            except requests.exceptions.RequestException as e:
                print(f"Erro ao obter produtos REST seguros de {producer['nome']}")
        return all_secure_products

    def validate_rest_response(self, response, request_description, producer_name):
        try:
            content = response.json()
            required_fields = ['assinatura', 'certificado', 'mensagem']
            if not all(field in content for field in required_fields):
                print(f"Resposta incompleta para {request_description}")
                return False

            signature = content['assinatura']
            certificate_pem = content['certificado'].encode('utf-8')
            message = content['mensagem']

            with open("manager_public_key.pem", "r") as f:
                gestor_public_key_pem = f.read()

            if not self.validate_certificate(certificate_pem, gestor_public_key_pem, producer_name):
                return False

            if not self.validate_signature(signature, message, certificate_pem, producer_name):
                return False

            return True

        except (json.JSONDecodeError, KeyError, TypeError) as e:
            print(f"Erro ao processar resposta REST para {producer_name}")
            return False

    def buy_secure_rest_product(self):
        secure_products = self.fetch_secure_rest_products()

        if not secure_products:
            print("Nenhum produto seguro disponível para compra.")
            return

        print("Produtores seguros disponíveis:")
        for i, producer_name in enumerate(secure_products.keys()):
            print(f"{i + 1}. {producer_name}")

        while True:
            try:
                producer_index = int(input("Escolha um produtor pelo número: ")) - 1
                if 0 <= producer_index < len(secure_products):
                    selected_producer_name = list(secure_products.keys())[producer_index]
                    available_products = secure_products[selected_producer_name]
                    break
                else:
                    print("Índice de produtor inválido.")
            except ValueError:
                print("Entrada inválida. Por favor, insira um número.")

        print(f"Produtos disponíveis de {selected_producer_name}:")
        for i, product in enumerate(available_products):
            print(f"{i + 1}. {product['produto']} (Categoria: {product['categoria']}, Preço: {product['preco']})")

        while True:
            try:
                product_index = int(input("Escolha um produto pelo número: ")) - 1
                if 0 <= product_index < len(available_products):
                    selected_product = available_products[product_index]
                    break
                else:
                    print("Índice de produto inválido.")
            except ValueError:
                print("Entrada inválida. Por favor, insira um número.")

        quantity = int(input(f"Digite a quantidade de {selected_product['produto']} que deseja comprar: "))

        rest_producers = self.get_rest_producers()
        for producer in rest_producers:
            if producer['nome'] == selected_producer_name:
                try:
                    base_url = f"http://{producer['ip']}:{producer['porta']}"
                    response = requests.post(f"{base_url}/secure/comprar/{selected_product['produto']}/{quantity}")

                    if response.status_code == 200:
                        print("Compra realizada com sucesso")
                        print(response.json().get('mensagem', 'Resposta do servidor desconhecida'))
                    else:
                        print(f"Erro na compra: {response.status_code} - {response.text}")


                except requests.exceptions.RequestException as e:
                    print(f"Erro de comunicação com o servidor REST de {producer_name}")

    def display_secure_products(self):
        secure_products = self.fetch_secure_rest_products()

        if not secure_products:
            print("Nenhum produto seguro disponível.")
            return

        print("=====================================")
        print("Produtos Seguros disponíveis:")
        for producer_name, products in secure_products.items():
            print(f"\nProdutor: {producer_name}")
            for product in products:
                print(
                    f"  - {product.get('produto', 'Sem nome')} (Categoria: {product.get('categoria', 'N/A')}, Quantidade: {product.get('quantidade', 'N/A')}, Preço: {product.get('preco', 'N/A')})")
        print("=====================================")

    def display_products(self):
        if not self.products:
            print("  Nenhum produto disponível.")
            return

        print("=====================================")
        print("  Produtos disponíveis:")
        for producer_address, products in self.products.items():
            print(f"  Produtor {producer_address}:")

            categories = set()
            for product in products:
                if 'categoria' in product:
                    categories.add(product['categoria'])
                else:
                    print(f"Aviso: Produto '{product.get('produto', 'sem nome')}' não possui categoria.")

            for category in categories:
                print(f"    Categoria: {category}")
                for product in products:
                    if product.get('categoria') == category:
                        quantidade = product.get('quantidade', 'N/A')
                        print(
                            f"      - {product.get('produto', 'sem nome')} - Quantidade: {quantidade} unidades - Preço: {product.get('preco', 'N/A')}")

    def start(self):
        print("=====================================")
        print("  Bem-vindo ao Marketplace!")
        print("=====================================")

        config_file = "ProdutoresMarketplace.json"
        file_producers = self.get_producers_from_config(config_file)

        while True:
            if file_producers:

                print("=====================================")
                print("  O que você deseja fazer?")
                print("  1 - Comprar um produto")
                print("  2 - Ver produtos de uma categoria específica")
                print("  3 - Ver lista de todos os produtos")
                print("  4 - Listar Produtores Seguros")
                print("  5 - Comprar Produto Seguro")
                print("  6 - Sair")
                print("=====================================")
                opcao = input("Digite a opção: ")

                if opcao == "1":
                    comprar = input("Deseja comprar algum produto? (s/n): ")
                    if comprar.lower() == "s":
                        producer_address = input("Digite o endereço do produtor (ip:porta ): ")
                        is_rest_producer = input("É um produtor REST? (s/n): ")

                        if is_rest_producer.lower() == "s":
                            producer_ip, producer_port = producer_address.split(":")
                            product_name = input("Digite o nome do produto: ")
                            quantity = int(input("Digite a quantidade: "))
                            self.buy_rest_product(producer_ip, producer_port, product_name, quantity)
                        else:
                            product_name = input("Digite o nome do produto: ")
                            quantity = int(input("Digite a quantidade: "))
                            self.buy_product(producer_address, product_name, quantity)

                    else:
                        print("  Voltando ao menu principal...")
                elif opcao == "2":
                    self.update_products(file_producers)
                    all_categories = set()
                    for _, products in self.products.items():
                        for product in products:
                            if 'categoria' in product:
                                all_categories.add(product['categoria'].capitalize())

                    print("Categorias disponíveis:")
                    for i, category in enumerate(all_categories):
                        print(f"{i + 1} - {category}")

                    while True:
                        try:
                            selected_category_index = int(input("Escolha uma categoria: "))
                            if 1 <= selected_category_index <= len(all_categories):
                                break
                            else:
                                print("Índice de categoria inválido.")
                        except ValueError:
                            print("Entrada inválida. Por favor, insira um número.")

                    selected_category = list(all_categories)[selected_category_index - 1]

                    print(f"Produtos da categoria {selected_category}:")

                    for producer_address, products in self.products.items():
                        print(f"  Produtor {producer_address}:")
                        for product in products:
                            if product.get('categoria', '').capitalize() == selected_category:
                                quantidade = product.get('quantidade', 'N/A')
                                print(
                                    f"      - {product.get('produto', 'sem nome')} - Quantidade: {quantidade} unidades - Preço: {product.get('preco', 'N/A')}")

                    time.sleep(5)

                elif opcao == "3":
                    self.update_products(file_producers)
                    self.display_products()
                elif opcao == "4":
                    self.display_secure_products()
                elif opcao == "5":
                    self.buy_secure_rest_product()
                elif opcao == "6":
                    print("  Saindo do Marketplace...")
                    break
                else:
                    print("  Opção inválida. Tente novamente.")
            else:
                print("  Nenhum produtor encontrado no arquivo de configuração.")


if __name__ == "__main__":
    marketplace = Marketplace()
    marketplace.start()
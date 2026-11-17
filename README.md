# Stockwise — Planejamento de Cargas com Knapsack

Aplicação web acadêmica para planejar cargas de caminhão. O usuário escolhe os produtos candidatos, informa a capacidade e as dimensões internas do veículo e define um segundo limite por orçamento ou por quantidade total de unidades. O Algoritmo da Mochila encontra a combinação de maior valor agregado e um empacotador 3D valida a posição física de cada unidade.

O projeto usa Python, Flask e dois bancos SQLite:

- `instance/estoque.db`: produtos e quantidades físicas do inventário;
- `instance/cargas.db`: cargas pendentes e itens temporariamente reservados.

Cada produto possui peso e dimensões da embalagem (comprimento, largura e altura em centímetros). Cada carga possui as dimensões internas do caminhão. O sistema calcula posições `(x, y, z)`, permite rotações das caixas e exibe uma visualização 3D simples na prévia e na tela de liberação.

As telas de consulta permanecem disponíveis sem autenticação. Para cadastrar, editar ou excluir produtos, planejar cargas e liberar cargas é necessário entrar no sistema. O banco cria automaticamente o usuário inicial `admin` com a senha `admin`; a senha é armazenada com hash.

## Fluxo do sistema

1. Entre com `admin` / `admin` para alterar os dados.
2. Cadastre os produtos em **Produtos**.
3. Acesse **Planejar carga** e identifique o caminhão.
4. Informe sua capacidade máxima.
5. Informe comprimento, largura e altura internas do caminhão.
6. Escolha o segundo limite: orçamento ou quantidade de unidades.
7. Selecione os produtos e defina o mínimo obrigatório e o máximo permitido de cada um.
8. Calcule a prévia. O Knapsack maximiza o valor e o empacotador 3D remove somente unidades extras quando a combinação não cabe fisicamente.
9. Salve a carga. As unidades ficam reservadas e não podem ser usadas em outra carga.
10. Na tela **Liberar cargas**, confira os itens, posições e visualização 3D e libere o caminhão.
11. Ao liberar, as quantidades são baixadas do estoque e a carga é apagada das pendências.

Produtos com unidades reservadas não podem ser excluídos, e sua quantidade cadastrada não pode ficar abaixo da reserva existente.

## Executar no Windows e VS Code

Nesta máquina, o Python, o ambiente `.venv` e a extensão do VS Code já estão configurados. Para iniciar:

- clique duas vezes em `executar.bat`; ou
- abra **Executar e Depurar** no VS Code, escolha **Executar Stockwise** e pressione `F5`.

Também é possível usar o terminal:

```powershell
.venv\Scripts\python.exe app.py
```

Depois, acesse `http://127.0.0.1:5000`.

Em outro computador, prepare o ambiente com:

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

### Dados para demonstração

```powershell
.venv\Scripts\python.exe -m flask --app app seed-demo
```

O comando adiciona cinco produtos de demonstração com dimensões. Códigos já cadastrados são preservados; executar novamente não duplica os produtos.

Para recriar produtos e uma carga pendente com posições 3D em um único passo:

```powershell
.venv\Scripts\python.exe -m flask --app app seed-example
```

Esse comando substitui todos os produtos e cargas pendentes por dados de exemplo, preservando os usuários. Use-o apenas quando desejar recriar os dados de demonstração.

Para inicializar ou atualizar a estrutura dos bancos sem apagar os registros:

```powershell
.venv\Scripts\python.exe -m flask --app app init-db
```

Pesos são arredondados para três casas decimais e dimensões para duas. Medidas positivas que seriam arredondadas para zero são rejeitadas com uma mensagem de validação. Custo e valor agregado continuam aceitando zero.

### Catálogo amplo para testes

Os bancos incluídos no repositório foram preenchidos com 60 produtos e 913.400 unidades: acessórios pequenos, eletrodomésticos, móveis, materiais e embalagens de formatos variados. Há de 800 a 100.000 unidades por produto. Pesos estão em kg, dimensões em cm e custos em reais; todos os dados são fictícios para demonstração. Quando o produto é descrito como caixa, pacote ou kit, cada unidade cadastrada representa essa embalagem completa.

O script abaixo mostra os totais sem alterar os bancos:

```powershell
.venv\Scripts\python.exe scripts/populate_varied_inventory.py
```

Para substituir o estoque pelo catálogo amplo, use o mesmo comando com `--apply`. Ele cria uma cópia dos dois bancos em `../backups`, remove produtos e cargas de demonstração e preserva usuários. Se houver cargas com nomes que não começam com `Carga demonstração`, a operação é bloqueada. As cópias de segurança ficam fora do repositório.

A quantidade em estoque não é a quantidade obrigatória em uma carga. Para experimentar o planejamento com esse catálogo, selecione os produtos desejados e defina máximos menores por item, conforme o caminhão. O limite de 20.000 caixas por tentativa de encaixe e o limite de estados do Knapsack continuam em vigor.

## Algoritmo

O sistema implementa o **Knapsack limitado multidimensional** por programação dinâmica esparsa:

- é limitado pela quantidade disponível de cada produto e pelo máximo definido para a carga;
- sempre usa a capacidade do caminhão como primeira restrição;
- usa orçamento ou quantidade total como segunda restrição;
- inclui primeiro as quantidades mínimas para garantir a diversidade solicitada;
- executa o Knapsack sobre a capacidade restante, respeitando os máximos;
- maximiza a soma do valor agregado dos produtos selecionados.

Depois da otimização, o empacotador 3D usa pontos extremos e as seis rotações possíveis de cada caixa. Ele verifica limites e sobreposição em três eixos, preserva os mínimos obrigatórios e reduz unidades extras de menor valor relativo quando necessário.

As quantidades são decompostas em blocos binários. A programação dinâmica elimina estados dominados, reduzindo o uso de memória sem perder a solução exata. Cálculos acima de 250 mil estados não dominados são interrompidos para proteger o computador.

## Testes

```powershell
.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Os testes cobrem os dois modos de limite, comparação com força bruta, números decimais, CRUD, dimensões de produtos, empacotamento 3D, reservas, bancos separados e liberação com baixa de estoque. Também verificam os três comandos de banco sem contexto manual, execução repetida dos dados de exemplo e rejeição de medidas que seriam arredondadas para zero. Os testes utilizam bancos temporários, sem recriar os bancos locais do projeto.

## Estrutura

```text
estoque-knapsack/
├── app.py                  # Rotas, validações, bancos e algoritmo
├── schema.sql              # Estrutura do estoque.db
├── loads_schema.sql        # Estrutura do cargas.db
├── requirements.txt
├── executar.bat
├── static/                 # Estilos, ícone e JavaScript da interface
├── templates/              # Telas HTML
├── tests/                  # Testes automatizados
└── instance/
    ├── estoque.db
    └── cargas.db
```

O “valor agregado” é uma pontuação informada pelo usuário. Quanto maior a pontuação, maior a preferência do algoritmo pelo produto, sempre respeitando as restrições da carga.

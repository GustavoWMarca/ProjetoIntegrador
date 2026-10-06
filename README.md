# Stockwise — Planejamento de Cargas com Knapsack

Aplicação web acadêmica para planejar cargas de caminhão. O usuário escolhe os produtos candidatos, informa a capacidade do veículo e define um segundo limite por orçamento ou por quantidade total de unidades. O Algoritmo da Mochila encontra a combinação de maior valor agregado.

O projeto usa Python, Flask e dois bancos SQLite:

- `instance/estoque.db`: produtos e quantidades físicas do inventário;
- `instance/cargas.db`: cargas pendentes e itens temporariamente reservados.

## Fluxo do sistema

1. Cadastre os produtos em **Produtos**.
2. Acesse **Planejar carga** e identifique o caminhão.
3. Informe sua capacidade máxima.
4. Escolha o segundo limite: orçamento ou quantidade de unidades.
5. Selecione os produtos e defina o mínimo obrigatório e o máximo permitido de cada um.
6. Calcule a prévia e salve a carga. As unidades ficam reservadas e não podem ser usadas em outra carga.
7. Na tela **Liberar cargas**, confira os itens e libere o caminhão.
8. Ao liberar, as quantidades são baixadas do estoque e a carga é apagada das pendências.

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

## Algoritmo

O sistema implementa o **Knapsack limitado multidimensional** por programação dinâmica esparsa:

- é limitado pela quantidade disponível de cada produto e pelo máximo definido para a carga;
- sempre usa a capacidade do caminhão como primeira restrição;
- usa orçamento ou quantidade total como segunda restrição;
- inclui primeiro as quantidades mínimas para garantir a diversidade solicitada;
- executa o Knapsack sobre a capacidade restante, respeitando os máximos;
- maximiza a soma do valor agregado dos produtos selecionados.

As quantidades são decompostas em blocos binários. A programação dinâmica elimina estados dominados, reduzindo o uso de memória sem perder a solução exata. Cálculos acima de 250 mil estados não dominados são interrompidos para proteger o computador.

## Testes

```powershell
.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Os testes cobrem os dois modos de limite, comparação com força bruta, números decimais, CRUD, reservas, bancos separados e liberação com baixa de estoque.

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

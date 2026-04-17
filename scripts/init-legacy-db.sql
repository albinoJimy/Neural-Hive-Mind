-- Script de inicialização da base de dados legada
-- Para uso com docker-compose-fluxo-h.yml
--
# Este script cria tabelas de exemplo e dados de teste
# para simular um sistema legado a ser migrado via Fluxo H

-- Habilitar extensão para CDC (Change Data Capture)
CREATE EXTENSION IF NOT EXISTS "pgoutput";

-- ========================================
-- TABELAS LEGADAS
-- ========================================

-- Tabela de usuários legada
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    username VARCHAR(50) NOT NULL UNIQUE,
    email VARCHAR(100) NOT NULL,
    full_name VARCHAR(100),
    status VARCHAR(20) DEFAULT 'active',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Tabela de pedidos legada
CREATE TABLE IF NOT EXISTS orders (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL,
    total_amount DECIMAL(10,2) NOT NULL,
    status VARCHAR(20) DEFAULT 'pending',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

-- Tabela de produtos legada
CREATE TABLE IF NOT EXISTS products (
    id INTEGER PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    description TEXT,
    price DECIMAL(10,2) NOT NULL,
    stock INTEGER DEFAULT 0,
    category VARCHAR(50),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Tabela de itens do pedido legada
CREATE TABLE IF NOT EXISTS order_items (
    id INTEGER PRIMARY KEY,
    order_id INTEGER NOT NULL,
    product_id INTEGER NOT NULL,
    quantity INTEGER NOT NULL,
    unit_price DECIMAL(10,2) NOT NULL,
    FOREIGN KEY (order_id) REFERENCES orders(id),
    FOREIGN KEY (product_id) REFERENCES products(id)
);

-- ========================================
-- DADOS DE EXEMPLO
-- ========================================

-- Inserir usuários de exemplo
INSERT INTO users (id, username, email, full_name, status) VALUES
(1, 'joao.silva', 'joao.silva@example.com', 'João Silva', 'active'),
(2, 'maria.santos', 'maria.santos@example.com', 'Maria Santos', 'active'),
(3, 'pedro.ferreira', 'pedro.ferreira@example.com', 'Pedro Ferreira', 'active'),
(4, 'ana.costa', 'ana.costa@example.com', 'Ana Costa', 'inactive'),
(5, 'carlos.mendes', 'carlos.mendes@example.com', 'Carlos Mendes', 'active');

-- Inserir produtos de exemplo
INSERT INTO products (id, name, description, price, stock, category) VALUES
(1, 'Notebook Dell Latitude', 'Notebook corporativo Dell Latitude 5420', 4500.00, 50, 'eletronicos'),
(2, 'Mouse Logitech MX Master', 'Mouse sem fio Logitech MX Master 3', 350.00, 200, 'acessorios'),
(3, 'Teclado Mecânico Keychron', 'Teclado mecânico Keychron K2', 600.00, 100, 'acessorios'),
(4, 'Monitor Samsung 27"', 'Monitor Samsung LED 27 polegadas', 1200.00, 75, 'eletronicos'),
(5, 'Webcam Logitech C920', 'Webcam Logitech C920 HD', 450.00, 150, 'acessorios');

-- Inserir pedidos de exemplo
INSERT INTO orders (id, user_id, total_amount, status) VALUES
(1, 1, 4850.00, 'completed'),
(2, 2, 1200.00, 'pending'),
(3, 3, 1050.00, 'shipped'),
(4, 1, 600.00, 'completed'),
(5, 5, 1650.00, 'pending');

-- Inserir itens dos pedidos
INSERT INTO order_items (id, order_id, product_id, quantity, unit_price) VALUES
(1, 1, 1, 1, 4500.00),
(2, 1, 2, 1, 350.00),
(3, 2, 4, 1, 1200.00),
(4, 3, 1, 1, 4500.00),
(5, 3, 3, 1, 600.00),
(6, 4, 3, 1, 600.00),
(7, 5, 4, 1, 1200.00),
(8, 5, 2, 1, 350.00),
(9, 5, 5, 1, 450.00);

-- ========================================
-- ÍNDICES (para performance)
-- ========================================

CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
CREATE INDEX IF NOT EXISTS idx_users_status ON users(status);
CREATE INDEX IF NOT EXISTS idx_orders_user_id ON orders(user_id);
CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status);
CREATE INDEX IF NOT EXISTS idx_orders_created_at ON orders(created_at);
CREATE INDEX IF NOT EXISTS idx_products_category ON products(category);

-- ========================================
-- ESTATÍSTICAS
-- ========================================

-- Mostrar estatísticas da base de dados
SELECT
    'users' as table_name,
    COUNT(*) as row_count
FROM users
UNION ALL
SELECT
    'orders',
    COUNT(*)
FROM orders
UNION ALL
SELECT
    'products',
    COUNT(*)
FROM products
UNION ALL
SELECT
    'order_items',
    COUNT(*)
FROM order_items;

-- Mostrar amostra de dados
SELECT '=== USERS ===' as info;
SELECT * FROM users LIMIT 5;

SELECT '=== ORDERS ===' as info;
SELECT * FROM orders LIMIT 5;

SELECT '=== PRODUCTS ===' as info;
SELECT * FROM products LIMIT 5;

SELECT '=== ORDER ITEMS ===' as info;
SELECT * FROM order_items LIMIT 5;

-- ========================================
-- NOTIFICAÇÃO
-- ========================================

DO $$
BEGIN
    RAISE NOTICE 'Base de dados legada inicializada com sucesso!';
    RAISE NOTICE 'Tabelas criadas: users, orders, products, order_items';
    RAISE NOTICE 'Total de registros: % users, % orders',
        (SELECT COUNT(*) FROM users),
        (SELECT COUNT(*) FROM orders);
END $$;

\# Part 2: Database Schema Design



\## 1. Database Schema (SQL DDL)



```sql

\-- ============================================================

\-- COMPANIES

\-- ============================================================

CREATE TABLE companies (

&#x20;   id         SERIAL       PRIMARY KEY,

&#x20;   name       VARCHAR(255) NOT NULL,

&#x20;   created\_at TIMESTAMPTZ  NOT NULL DEFAULT NOW()

);



\-- ============================================================

\-- WAREHOUSES

\-- ============================================================

CREATE TABLE warehouses (

&#x20;   id         SERIAL       PRIMARY KEY,

&#x20;   company\_id INTEGER      NOT NULL REFERENCES companies(id) ON DELETE RESTRICT,

&#x20;   name       VARCHAR(255) NOT NULL,

&#x20;   location   VARCHAR(500),

&#x20;   created\_at TIMESTAMPTZ  NOT NULL DEFAULT NOW()

);



CREATE INDEX idx\_warehouses\_company\_id ON warehouses(company\_id);



\-- ============================================================

\-- SUPPLIERS

\-- ============================================================

CREATE TABLE suppliers (

&#x20;   id         SERIAL       PRIMARY KEY,

&#x20;   name       VARCHAR(255) NOT NULL,

&#x20;   email      VARCHAR(255),

&#x20;   phone      VARCHAR(50),

&#x20;   created\_at TIMESTAMPTZ  NOT NULL DEFAULT NOW()

);



\-- ============================================================

\-- PRODUCTS

\-- ============================================================

CREATE TABLE products (

&#x20;   id          SERIAL       PRIMARY KEY,

&#x20;   company\_id  INTEGER      NOT NULL REFERENCES companies(id) ON DELETE RESTRICT,

&#x20;   sku         VARCHAR(64)  NOT NULL,

&#x20;   name        VARCHAR(255) NOT NULL,

&#x20;   description TEXT,

&#x20;   price\_cents INTEGER      NOT NULL CHECK (price\_cents >= 0),

&#x20;   is\_bundle   BOOLEAN      NOT NULL DEFAULT FALSE,

&#x20;   is\_active   BOOLEAN      NOT NULL DEFAULT TRUE,

&#x20;   created\_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW(),



&#x20;   CONSTRAINT uq\_products\_company\_sku UNIQUE (company\_id, sku)

);



CREATE INDEX idx\_products\_company\_id ON products(company\_id);

CREATE INDEX idx\_products\_sku        ON products(sku);



\-- ============================================================

\-- PRODUCT BUNDLES

\-- ============================================================

CREATE TABLE product\_bundle\_items (

&#x20;   bundle\_product\_id    INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,

&#x20;   component\_product\_id INTEGER NOT NULL REFERENCES products(id) ON DELETE RESTRICT,

&#x20;   quantity             INTEGER NOT NULL CHECK (quantity > 0),



&#x20;   PRIMARY KEY (bundle\_product\_id, component\_product\_id),

&#x20;   CONSTRAINT chk\_no\_self\_bundle CHECK (bundle\_product\_id <> component\_product\_id)

);



CREATE INDEX idx\_bundle\_items\_component ON product\_bundle\_items(component\_product\_id);



\-- ============================================================

\-- SUPPLIER PRODUCTS

\-- ============================================================

CREATE TABLE supplier\_products (

&#x20;   supplier\_id      INTEGER NOT NULL REFERENCES suppliers(id) ON DELETE CASCADE,

&#x20;   product\_id       INTEGER NOT NULL REFERENCES products(id)  ON DELETE CASCADE,

&#x20;   unit\_cost\_cents  INTEGER CHECK (unit\_cost\_cents >= 0),

&#x20;   lead\_time\_days   INTEGER CHECK (lead\_time\_days >= 0),

&#x20;   is\_preferred     BOOLEAN NOT NULL DEFAULT FALSE,

&#x20;   created\_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),



&#x20;   PRIMARY KEY (supplier\_id, product\_id)

);



CREATE INDEX idx\_supplier\_products\_product ON supplier\_products(product\_id);



\-- ============================================================

\-- INVENTORY

\-- ============================================================

CREATE TABLE inventory (

&#x20;   id           SERIAL  PRIMARY KEY,

&#x20;   product\_id   INTEGER NOT NULL REFERENCES products(id)   ON DELETE RESTRICT,

&#x20;   warehouse\_id INTEGER NOT NULL REFERENCES warehouses(id) ON DELETE RESTRICT,

&#x20;   quantity     INTEGER NOT NULL DEFAULT 0 CHECK (quantity >= 0),

&#x20;   updated\_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),



&#x20;   CONSTRAINT uq\_inventory\_product\_warehouse UNIQUE (product\_id, warehouse\_id)

);



CREATE INDEX idx\_inventory\_warehouse\_id ON inventory(warehouse\_id);

CREATE INDEX idx\_inventory\_product\_id   ON inventory(product\_id);



\-- ============================================================

\-- INVENTORY TRANSACTIONS

\-- ============================================================

CREATE TYPE inventory\_txn\_type AS ENUM (

&#x20;   'receive',

&#x20;   'sale',

&#x20;   'adjustment',

&#x20;   'transfer',

&#x20;   'return'

);



CREATE TABLE inventory\_transactions (

&#x20;   id               BIGSERIAL    PRIMARY KEY,

&#x20;   product\_id       INTEGER      NOT NULL REFERENCES products(id)   ON DELETE RESTRICT,

&#x20;   warehouse\_id     INTEGER      NOT NULL REFERENCES warehouses(id) ON DELETE RESTRICT,

&#x20;   transaction\_type inventory\_txn\_type NOT NULL,

&#x20;   quantity\_delta   INTEGER      NOT NULL,

&#x20;   quantity\_after   INTEGER      NOT NULL CHECK (quantity\_after >= 0),

&#x20;   reference\_id     VARCHAR(255),

&#x20;   note             TEXT,

&#x20;   created\_by       INTEGER      REFERENCES users(id) ON DELETE SET NULL,

&#x20;   created\_at       TIMESTAMPTZ  NOT NULL DEFAULT NOW()

);



CREATE INDEX idx\_inv\_txn\_product\_id   ON inventory\_transactions(product\_id);

CREATE INDEX idx\_inv\_txn\_warehouse\_id ON inventory\_transactions(warehouse\_id);

CREATE INDEX idx\_inv\_txn\_created\_at   ON inventory\_transactions(created\_at DESC);

CREATE INDEX idx\_inv\_txn\_reference    ON inventory\_transactions(reference\_id);



\-- ============================================================

\-- USERS

\-- ============================================================

CREATE TABLE users (

&#x20;   id         SERIAL       PRIMARY KEY,

&#x20;   company\_id INTEGER      NOT NULL REFERENCES companies(id) ON DELETE RESTRICT,

&#x20;   email      VARCHAR(255) NOT NULL UNIQUE,

&#x20;   name       VARCHAR(255) NOT NULL,

&#x20;   created\_at TIMESTAMPTZ  NOT NULL DEFAULT NOW()

);

```



\---



\## 2. Gaps and Clarifying Questions



\### Scope and Multi-Tenancy



1\. Are SKUs unique globally or scoped per company?

2\. Are suppliers shared across companies or company-specific?



\### Inventory Behavior



3\. Should inventory be allowed to go negative (backorders)?

4\. How should warehouse transfers be modeled — single record or dual transactions?

5\. Do returns immediately affect sellable inventory?



\### Bundles



6\. Should bundle sales reduce component inventory or bundle inventory?

7\. Are nested bundles allowed?

8\. How is bundle pricing determined?



\### Suppliers



9\. Can products have multiple suppliers and how is the preferred supplier selected?

10\. Should supplier costs and lead times be versioned historically?



\### Auditing and Permissions



11\. Is auditing required beyond inventory (e.g., product updates)?

12\. Should users have warehouse-level permissions?



\---



\## 3. Design Decisions and Justifications



\### Inventory Design



The `inventory` table stores current stock for fast reads, while `inventory\_transactions` stores all changes for auditing. This avoids expensive aggregation queries and ensures traceability.



\### Many-to-Many Relationships



Junction tables (`supplier\_products`, `product\_bundle\_items`) are used to maintain normalization and allow additional attributes like cost and quantity.



\### Bundle Modeling



Bundles are implemented using a self-referential relationship in `product\_bundle\_items`. Recursive validation (cycle detection) is handled at the application layer.



\### SKU Scoping



SKUs are scoped per company using a composite unique constraint. This avoids unnecessary global conflicts in multi-tenant systems.



\### Indexing Strategy



Indexes are added on frequently queried columns such as foreign keys and timestamps to ensure efficient joins and lookups.



\### Data Integrity



Foreign keys and constraints enforce correctness at the database level, reducing reliance on application logic.



\### Scalability



The transaction table uses `BIGSERIAL` to handle large volumes. Future optimizations may include partitioning based on time.




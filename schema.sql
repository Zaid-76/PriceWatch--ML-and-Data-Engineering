--
-- PostgreSQL database dump
--

\restrict HP2EfceLk27zxaWOp2kuhVyV3vZGmhI8ksdu7R2hP2ZpBjvaKtHHORiL8nEkvPJ

-- Dumped from database version 16.15 (Debian 16.15-1.pgdg13+2)
-- Dumped by pg_dump version 16.15 (Debian 16.15-1.pgdg13+2)

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: public; Type: SCHEMA; Schema: -; Owner: -
--

CREATE SCHEMA public;


--
-- Name: SCHEMA public; Type: COMMENT; Schema: -; Owner: -
--

COMMENT ON SCHEMA public IS 'standard public schema';


SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: companies; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.companies (
    company_id bigint NOT NULL,
    symbol character varying(20) NOT NULL,
    currency character varying(10) NOT NULL,
    exchange character varying(20),
    exchange_timezone character varying(30),
    mic_code character varying(20),
    type character varying(30),
    meta_data_fetched_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: companies_company_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.companies_company_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: companies_company_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.companies_company_id_seq OWNED BY public.companies.company_id;


--
-- Name: stock_predictions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.stock_predictions (
    prediction_id bigint NOT NULL,
    company_id bigint NOT NULL,
    feature_date date NOT NULL,
    target_date date NOT NULL,
    predicted_return double precision NOT NULL,
    model_run_id text NOT NULL,
    predicted_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT valid_prediction_dates CHECK ((target_date > feature_date))
);


--
-- Name: stock_predictions_prediction_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.stock_predictions ALTER COLUMN prediction_id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME public.stock_predictions_prediction_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: stock_prices; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.stock_prices (
    price_id bigint NOT NULL,
    company_id bigint NOT NULL,
    price_date date NOT NULL,
    open_price numeric(12,4) NOT NULL,
    high_price numeric(12,4) NOT NULL,
    low_price numeric(12,4) NOT NULL,
    close_price numeric(12,4) NOT NULL,
    volume bigint,
    ingested_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT valid_daily_price_range CHECK (((low_price <= high_price) AND ((open_price >= low_price) AND (open_price <= high_price)) AND ((close_price >= low_price) AND (close_price <= high_price))))
);


--
-- Name: stock_prices_price_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.stock_prices_price_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: stock_prices_price_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.stock_prices_price_id_seq OWNED BY public.stock_prices.price_id;


--
-- Name: companies company_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.companies ALTER COLUMN company_id SET DEFAULT nextval('public.companies_company_id_seq'::regclass);


--
-- Name: stock_prices price_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.stock_prices ALTER COLUMN price_id SET DEFAULT nextval('public.stock_prices_price_id_seq'::regclass);


--
-- Name: companies companies_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.companies
    ADD CONSTRAINT companies_pkey PRIMARY KEY (company_id);


--
-- Name: stock_predictions stock_predictions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.stock_predictions
    ADD CONSTRAINT stock_predictions_pkey PRIMARY KEY (prediction_id);


--
-- Name: stock_prices stock_prices_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.stock_prices
    ADD CONSTRAINT stock_prices_pkey PRIMARY KEY (price_id);


--
-- Name: companies unique_company_listing; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.companies
    ADD CONSTRAINT unique_company_listing UNIQUE (symbol, exchange);


--
-- Name: stock_prices unique_company_price_date; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.stock_prices
    ADD CONSTRAINT unique_company_price_date UNIQUE (company_id, price_date);


--
-- Name: stock_predictions unique_stock_prediction; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.stock_predictions
    ADD CONSTRAINT unique_stock_prediction UNIQUE (company_id, feature_date, model_run_id);


--
-- Name: stock_predictions stock_predictions_company_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.stock_predictions
    ADD CONSTRAINT stock_predictions_company_id_fkey FOREIGN KEY (company_id) REFERENCES public.companies(company_id);


--
-- Name: stock_prices stock_prices_company_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.stock_prices
    ADD CONSTRAINT stock_prices_company_id_fkey FOREIGN KEY (company_id) REFERENCES public.companies(company_id);


--
-- PostgreSQL database dump complete
--

\unrestrict HP2EfceLk27zxaWOp2kuhVyV3vZGmhI8ksdu7R2hP2ZpBjvaKtHHORiL8nEkvPJ


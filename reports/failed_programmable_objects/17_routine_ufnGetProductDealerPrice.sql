-- ERROR:
(psycopg2.errors.SyntaxError) too few parameters specified for RAISE
CONTEXT:  compilation of PL/pgSQL function "ufnGetProductDealerPrice" near line 4

[SQL: 
CREATE OR REPLACE PROCEDURE "dbo"."ufnGetProductDealerPrice"()
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE NOTICE 'Original MSSQL routine requires manual SQL dialect review.';
    RAISE NOTICE 'CREATE FUNCTION "dbo"."ufnGetProductDealerPrice"(@ProductID "int", @OrderDate "datetime")
RETURNS "money"
AS
-- Returns the dealer price for the product on a specific date.
BEGIN
    DECLARE @DealerPrice money;
    DECLARE @DealerDiscount money;

    SET @DealerDiscount = 0.60  -- 60%% of list price

    SELECT @DealerPrice = plph."ListPrice" * @DealerDiscount
    FROM "Production"."Product" p
        INNER JOIN "Production"."ProductListPriceHistory" plph
        ON p."ProductID" = plph."ProductID"
            AND p."ProductID" = @ProductID
            AND @OrderDate BETWEEN plph."StartDate" AND COALESCE(plph."EndDate", CONVERT(datetime, ''99991231'', 112)); -- Make sure we get all the prices!

    RETURN @DealerPrice;
END;';
END;
$$;
]
(Background on this error at: https://sqlalche.me/e/20/f405)

-- SOURCE DEFINITION:

CREATE FUNCTION [dbo].[ufnGetProductDealerPrice](@ProductID [int], @OrderDate [datetime])
RETURNS [money]
AS
-- Returns the dealer price for the product on a specific date.
BEGIN
    DECLARE @DealerPrice money;
    DECLARE @DealerDiscount money;

    SET @DealerDiscount = 0.60  -- 60% of list price

    SELECT @DealerPrice = plph.[ListPrice] * @DealerDiscount
    FROM [Production].[Product] p
        INNER JOIN [Production].[ProductListPriceHistory] plph
        ON p.[ProductID] = plph.[ProductID]
            AND p.[ProductID] = @ProductID
            AND @OrderDate BETWEEN plph.[StartDate] AND COALESCE(plph.[EndDate], CONVERT(datetime, '99991231', 112)); -- Make sure we get all the prices!

    RETURN @DealerPrice;
END;

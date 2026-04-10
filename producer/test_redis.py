import asyncio
from state import RedisState

async def test_redis_state():
    """
    Script de prueba para verificar la conexión y lógica atómica con Redis.
    """
    print("🚀 Iniciando test de Redis...")
    # Conectamos a localhost porque el script se ejecuta desde el host,
    # y el puerto de Redis está expuesto en el docker-compose.
    state = RedisState(host='localhost')

    symbol = "BTCUSDT_TEST"
    
    try:
        # 1. Limpiar estado previo para un test limpio
        await state.client.delete(symbol)
        print(f"🧹 Estado previo de '{symbol}' limpiado.")

        # 2. Obtener valor inicial
        initial_ts = await state.get_last_seen(symbol)
        print(f"Valor inicial para {symbol}: {initial_ts}")
        assert initial_ts == 0, "El valor inicial debería ser 0"

        # 3. Actualizar con un valor mayor
        print("Actualizando con timestamp 100...")
        updated = await state.update_if_newer(symbol, 100)
        print(f"¿Se actualizó?: {updated}")
        assert updated is True, "Debería actualizarse si el nuevo valor es mayor"
        current_ts = await state.get_last_seen(symbol)
        print(f"Valor actual para {symbol}: {current_ts}")
        assert current_ts == 100, "El timestamp debería ser 100"

        # 4. Intentar actualizar con un valor menor
        print("Intentando actualizar con timestamp 50 (no debería cambiar)...")
        updated = await state.update_if_newer(symbol, 50)
        print(f"¿Se actualizó?: {updated}")
        assert updated is False, "No debería actualizarse si el nuevo valor es menor"
        current_ts = await state.get_last_seen(symbol)
        print(f"Valor actual para {symbol}: {current_ts}")
        assert current_ts == 100, "El timestamp debería seguir siendo 100"

        # 5. Intentar actualizar con el mismo valor
        print("Intentando actualizar con timestamp 100 (no debería cambiar)...")
        updated = await state.update_if_newer(symbol, 100)
        print(f"¿Se actualizó?: {updated}")
        assert updated is False, "No debería actualizarse con el mismo valor"
        current_ts = await state.get_last_seen(symbol)
        print(f"Valor actual para {symbol}: {current_ts}")
        assert current_ts == 100, "El timestamp debería seguir siendo 100"

        # 6. Actualizar con un valor mayor de nuevo
        print("Actualizando con timestamp 150...")
        updated = await state.update_if_newer(symbol, 150)
        print(f"¿Se actualizó?: {updated}")
        assert updated is True, "Debería actualizarse de nuevo con un valor mayor"
        current_ts = await state.get_last_seen(symbol)
        print(f"Valor actual para {symbol}: {current_ts}")
        assert current_ts == 150, "El timestamp debería ser 150"

        print("\n✅ ¡Todas las pruebas pasaron con éxito!")

    except AssertionError as e:
        print(f"\n❌ Test fallido: {e}")
    except Exception as e:
        print(f"\n💥 Error durante el test: {e}")
    finally:
        # Limpiar la clave de test y cerrar conexión
        await state.client.delete(symbol)
        await state.close()
        print("🚪 Conexión cerrada y clave de test eliminada.")


if __name__ == "__main__":
    asyncio.run(test_redis_state())

# Wersja silnika obliczeniowego. Podbijamy przy KAŻDEJ zmianie logiki wyceny
# (np. dopłata porównawcza, podciąganie, współczynniki), żeby wyniki policzone
# starszym silnikiem i zapisane w cache (stats.json, compare.json, billing.json)
# zostały automatycznie przeliczone — inaczej Pulpit/Historia/Porównanie pokazują
# rozjechane liczby, dopóki użytkownik ręcznie nie przeliczy miesiąca.
# v3: listy badań po stawce 0 zł (jednostki + lekarze), marża per priorytet.
# v4: WSPARCIE doliczane do przychodu jednostek (Pulpit/Mapa/Porównanie); dopłata
#     porównawcza zbiorczo w podsumowaniu jednostki (bez zmiany kwoty przychodu).
ENGINE_VERSION = 4

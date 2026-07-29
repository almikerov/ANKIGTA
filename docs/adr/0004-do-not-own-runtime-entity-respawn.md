# Do not make ANKIGTA own Runtime Instance respawn

ANKIGTA наблюдает жизненный цикл Runtime Instance, но не воскрешает ped, не возвращает уничтоженный vehicle и не пересоздаёт object. Респавном владеет карта или создавший сущность игровой ресурс; при появлении экземпляра с тем же постоянным ID сохранённый Spatial Link снова становится доступен.


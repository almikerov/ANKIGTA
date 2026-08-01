# ANKIGTA v1

Status: ready-for-agent

## Problem Statement

Пользователь изучает карточки в Anki, но хочет связывать запоминание не только
с экраном Reviewer, а с конкретными местами и сущностями игрового мира
MTA:SA. Ему нужен однопользовательский инструмент, в котором object, vehicle
или ped из Map Editor можно связать с Anki Card, встретить эту цель в мире,
открыть вопрос и ответ, передать Again/Hard/Good/Easy штатному планировщику
Anki и затем продолжить пространственное обучение.

Продукт должен сохранять Spatial Link после переименования карты, движения или
уничтожения Runtime Instance и после перезапусков. При этом Anki должна
оставаться единственным владельцем содержания и расписания, а MTA — владельцем
игрового представления. Потеря ответа, закрытие Anki, перезапуск MTA или
незавершённая оценка не должны превращать одну Review Transaction в две.

Stock MTA Map Editor и stock MTA CEF имеют подтверждённые ограничения.
ANKIGTA v1 сознательно принимает неатомарное сохранение карты, отсутствие
защиты от внешнего изменения `.map`, best-effort отображение карточек,
card-visible неработающий `window.mta` stub и возможность перехода карточной
поверхности на внешний сайт. Эти ограничения не должны маскироваться под более
сильные гарантии.

## Solution

ANKIGTA v1 состоит из трёх взаимодействующих частей:

- server-side MTA resource хранит игровое состояние, Spatial Link, настройки
  мира и Change History, авторизует Study Player и является единственным
  MTA-шлюзом к companion control API;
- MTA client показывает F7, HUD, Review Mode и stock MTA CEF, управляет вводом,
  звуком, камерой и локальным размещением UI;
- companion add-on работает внутри уже запущенного пользователем Anki Desktop,
  владеет Companion Connection, collection identity, `ANKIGTA Session`,
  Exact Card Admission и durable Review Transaction journal.

Study Player — единственная вошедшая MTA-учётная запись с административным
правом ACL. Он выбирает одну Bound Anki Collection и запускает обучение явным
действием. Companion add-on строит из уникальных доступных карточек Active Map
Set настоящую rescheduling filtered deck `ANKIGTA Session`. Для ручного или
пространственного открытия Card X add-on временно перестраивает эту же колоду
в X-only набор, убеждается, что X стала scheduler-top, и только после этого
разрешает штатную оценку через Anki.

Постоянная идентичность карты хранится в EDF custom child, а идентичность
Map Entity — в element data/EDF property. ANKIGTA не редактирует `.map` в
фоне. Новая связь остаётся Pending Map Save, пока после обычного Save Map
Editor не выполнен независимый read-back однозначных ID.

Companion Connection использует только numeric IPv4 loopback `127.0.0.1`.
Привилегированный control API доступен только server-side Lua. Карточный CEF
получает HTML и media через отдельный read-only content endpoint по
короткоживущей per-render capability и не получает companion control
operations или постоянный connection token.

Основная проверочная граница спецификации — наблюдаемый end-to-end сценарий на
настоящих поддерживаемых Anki Desktop, MTA Server и MTA Client. Контрактные
тесты ниже этой границы используются только для детерминированного внедрения
сбоев, проверки durable recovery и валидации протокола.

Обычные implementation/review chats не имеют права запускать или изменять
установленный MTA/GTA. Они работают внутри repository, используют отдельное
read-only дерево MTA source и официальные manuals, создают repository-local
tests/harnesses и готовят manual runtime checklist. Выполнение настоящего MTA,
GTA, Map Editor или CEF runtime является отдельной явно разрешённой
пользователем validation-задачей; без неё соответствующий результат остаётся
`not run`, а не объявляется passed.

## User Stories

1. As a Study Player, I want ANKIGTA features to be available only to my
   authenticated MTA Admin account, so that ordinary players cannot access my
   collection or study controls.

   Acceptance criteria:

   - Given an account with the required MTA ACL right, when it logs in, then F7,
     HUD, Review Mode, Spatial Link actions and Companion Connection are
     available.
   - Given an ordinary player, when it sends any ANKIGTA client event, then the
     server rejects it and exposes no card or collection data.
   - Other players may remain on the server, but they receive no independent
     study state, links, markers or collection.

2. As a Study Player, I want to install and update the companion add-on
   manually, so that ANKIGTA does not modify my Anki add-on directory.

   Acceptance criteria:

   - ANKIGTA documentation provides installation, update and removal steps.
   - ANKIGTA never downloads an add-on package, edits the add-on directory or
     restarts Anki to install/update it.
   - A missing or nonresponsive add-on appears as an ordinary connection
     failure, not as a separate installer or compatibility screen.

3. As a Study Player, I want ANKIGTA to connect to an already running Anki
   automatically, so that normal startup requires no manual port or token copy.

   Acceptance criteria:

   - On first setup, the add-on asks once for the MTA resource folder, chooses a
     free loopback port, generates a token and publishes one versioned
     connection configuration.
   - MTA reads the published configuration and connects only to
     `127.0.0.1`; it never falls back to `::1`, LAN or an external interface.
   - Establishing Companion Connection does not create `ANKIGTA Session`,
     enable spatial activation or open Review Mode.

4. As a Study Player, I want a manual connection fallback, so that I can
   diagnose or recover a broken automatic configuration.

   Acceptance criteria:

   - Advanced settings exist on the add-on and MTA sides for replacement port
     and token values.
   - Editing either value enables Manual Connection Mode only on that side;
     automatic publication does not overwrite it.
   - A mismatch blocks connection with a specific error until both sides are
     manually aligned or both explicitly return to Automatic Connection Mode.
   - The existing token is masked and never displayed or written to ordinary
     diagnostic logs.

5. As a Study Player, I want to disable the token explicitly, so that local
   debugging is possible when I accept the weaker mode.

   Acceptance criteria:

   - Token protection is enabled and generated by default.
   - An empty token is possible only after explicit user action and produces a
     dismissible warning.
   - Protected requests validate the token before operation dispatch.
   - v1 documents that the local Windows machine and its processes are trusted;
     the token is not claimed to resist local malware or an administrator.

6. As a Study Player, I want connection failures to be bounded and legible, so
   that a missing add-on cannot freeze MTA.

   Acceptance criteria:

   - An ordinary control request ends within 5 seconds.
   - A read-only Transport Request may retry once with the same `requestId`;
     a rating never creates a new logical Review Transaction after timeout.
   - A rebuild may run for up to 30 seconds with progress and cancellation.
   - Absent, delayed, malformed or disconnected companion behavior releases
     the UI and reports a categorized error.
   - `Подключиться` is always available while disconnected and triggers an
     immediate attempt without disabling background auto-detection.

7. As a Study Player, I want automatic reconnection without automatic study
   startup, so that recovery cannot unexpectedly open cards or change Anki.

   Acceptance criteria:

   - Reopening Anki or restarting either endpoint restores Companion Connection
     automatically when configuration is valid.
   - Reconnection first reconciles unfinished Review Transaction records.
   - After reconciliation ANKIGTA remains paused, with no filtered deck,
     spatial activation or automatically reopened F7/Review Mode.
   - The user must choose `Начать обучение` again.

8. As a Study Player, I want one explicit Bound Anki Collection, so that equal
   numeric card IDs in different profiles never collide.

   Acceptance criteria:

   - Anki Card Identity is always `collection UUID + cardId`.
   - The collection UUID is add-on-owned, stored in collection configuration
     and survives restart and profile rename.
   - Profile name, directory and `cardId` alone are rejected as identity.
   - When another collection is open, study is paused and no link or rating is
     migrated to it.

9. As a Study Player, I want copied collections to receive an explicit identity
   decision, so that restoring an original and creating a new copy have
   different outcomes.

   Acceptance criteria:

   - If an instance with the UUID remains registered locally, a detected
     duplicate is automatically assigned a new UUID and starts without links.
   - If the prior instance is absent, the user chooses `Это прежняя коллекция`
     or `Это новая копия`; the latter is the default.
   - `Это прежняя коллекция` preserves existing Spatial Link, while
     `Это новая копия` atomically assigns a new UUID and inherits none.
   - No heuristic mapping by card content, note, deck or numeric `cardId` is
     performed.

10. As a Study Player, I want ANKIGTA to use the collection I opened myself,
    so that the add-on does not control Anki profiles.

    Acceptance criteria:

    - ANKIGTA never launches Anki Desktop and never switches profiles.
    - The UI identifies a wrong/open collection and asks the user to open the
      Bound Anki Collection.
    - An unrated Review Mode closes without mutation before the switch; a
      submitted Review Transaction is reconciled first.
    - `Outcome Unknown` prevents collection transition until resolved.

11. As a Study Player, I want my Anki content to remain authoritative, so that
    ANKIGTA does not fork my study data.

    Acceptance criteria:

    - Text, note fields, templates, CSS, media, Anki Tag, deck, scheduler state,
      suspended and buried status are read from Anki.
    - ANKIGTA writes back only Again/Hard/Good/Easy through Anki scheduling APIs.
    - Direct scheduling SQL writes, private queue mutation and an independent
      scheduler are absent.
    - Moving or editing a card preserves its Spatial Link while deleting its
      `cardId` creates Card missing.

12. As a Study Player, I want the Card Picker deck selection to be only a
    search filter, so that moving a linked card between decks does not disable
    it.

    Acceptance criteria:

    - The chosen deck initially filters Card Picker results.
    - Existing Spatial Link and `ANKIGTA Session` membership do not use that
      deck as a scope boundary.
    - Moving a linked card to another deck updates the displayed deck without
      changing Anki Card Identity.

13. As a map author, I want object, vehicle and ped from Map Editor to be
    manageable, so that all supported world targets behave consistently.

    Acceptance criteria:

    - Only Map Editor-created object, vehicle and ped elements are Map Entity.
    - Every managed record retains type, authored position, interior, dimension
      and its persistent identity.
    - Unmanaged or unloaded elements cannot be linked through world selection.

14. As a map author, I want maps and entities to have persistent IDs, so that
    renaming or moving them does not break Spatial Link.

    Acceptance criteria:

    - A map identity is an `ankigtaMapId` stored as an EDF custom child.
    - An entity identity is stored as element data/EDF property.
    - Coordinates, model and current Runtime Instance handle are never used as
      identity.
    - Resource/map rename preserves identity and existing links.

15. As a map author, I want ID assignment to use stock Map Editor Save, so that
    ANKIGTA does not rewrite `.map` behind the editor.

    Acceptance criteria:

    - Creating a link for an unidentified entity creates Pending Map Save.
    - Pending Map Save is excluded from `ANKIGTA Session`, statistics,
      activation and markers.
    - ANKIGTA performs no background `.map` write.
    - After normal Save, ANKIGTA observes the file change, independently reads
      map/entity IDs and activates only an unambiguous match.
    - `Проверить ещё раз` repeats read-back only.

16. As a map author, I want honest recovery from an unsaved or failed map
    operation, so that a guessed identity never silently becomes active.

    Acceptance criteria:

    - Closing or reloading without Save removes the pending link and notifies
      the user; Pending Map Save is not restored after restart.
    - Failed, partial or ambiguous read-back leaves the link pending.
    - The UI directs the user to repeat stock Save or use stock Editor recovery.
    - ANKIGTA does not claim whole-save atomicity, external-change protection or
      automatic repair of `.map`.

17. As a map author, I want copied ID collisions to be visible, so that two
    Map Entity do not silently share one Spatial Link identity.

    Acceptance criteria:

    - Duplicate map or entity IDs are detected before activation.
    - A collision blocks all ambiguous identities from active study.
    - A copied map offers original/renamed versus new-copy handling; a new copy
      receives new map/entity IDs and no automatic link transfer.
    - Clone, resource copy and Save As cases are covered by acceptance tests
      because stock Editor preserves embedded custom IDs.

18. As a Study Player, I want Map Entity metadata independent of `.map`, so
    that ordinary organization does not require resaving a map.

    Acceptance criteria:

    - Name, Entity Tag, radius, `Show radius` and Spatial Link metadata are
      stored in ANKIGTA server data after identity is confirmed.
    - Editing these fields does not write `.map`.
    - Entity Tag remains distinct from read-only Anki Tag.

19. As a Study Player, I want to create one Spatial Link per Map Entity, so
    that each world target has an unambiguous study target.

    Acceptance criteria:

    - A Map Entity has zero or one Spatial Link.
    - The same Anki Card may be linked from multiple entities after a warning
      listing existing uses.
    - Creating, replacing or removing a link never edits the Anki Card itself.

20. As a Study Player, I want `Replace card` and `Unlink`, so that I can repair
    links without deleting Map Entity metadata.

    Acceptance criteria:

    - `Unlink` requires confirmation naming the entity and card and removes only
      the Spatial Link.
    - `Replace card` previews old and new card identities and does not require
      an intermediate unlink.
    - Name, Entity Tag, radius and `Show radius` survive both operations.
    - An open review finishes under the old identity, then the session and HUD
      recalculate.

21. As a Study Player, I want Card missing to remain visible, so that deletion
    in Anki does not erase the world record.

    Acceptance criteria:

    - A missing `cardId` retains Map Entity metadata and the old link record.
    - It is excluded from session, activation and statistics.
    - `Replace card` is available; a newly created Anki card is never matched
      automatically.

22. As a Study Player, I want Entity missing to remain repairable, so that
    external map edits do not discard my card relationship.

    Acceptance criteria:

    - Entity missing is distinct from a destroyed Runtime Instance.
    - `Relink entity` chooses an unlinked live Map Entity by F7 list or Pick
      Entity, including another loaded map/interior/dimension.
    - The target keeps its own persistent IDs and receives the old Spatial Link,
      name, Entity Tag, radius and `Show radius`.
    - The operation previews changes, removes the old active missing record,
      enters Change History and is fully undoable.

23. As a Study Player, I want a persistent bounded Change History, so that I
    can recover from ordinary editing mistakes.

    Acceptance criteria:

    - The last 100 eligible user changes persist across F7 close and resource
      restart and support multi-step Undo/Redo.
    - A new change after Undo discards the remaining Redo branch.
    - Links, metadata, `Include in study` and ordinary user settings participate.
    - Connection settings, UI placement, Anki ratings/scheduling, runtime
      events, automatic IDs, backups and migrations do not participate.

24. As a Study Player, I want runtime motion and destruction handled without
    changing identity, so that dynamic world behavior does not lose links.

    Acceptance criteria:

    - Activation Zone and markers follow the current position of a live moving
      Runtime Instance.
    - Destruction removes active zone/marker but preserves Map Entity and link.
    - ANKIGTA never respawns object, vehicle or ped.
    - Reappearance with the same persistent identity restores availability.

25. As a Study Player, I want Pick Entity, so that I can select a visible world
    target without knowing its identifier.

    Acceptance criteria:

    - Entering Pick Entity hides F7, restores movement/look and blocks shooting,
      vehicle entry and ordinary interactions.
    - Left click selects the first visible managed Runtime Instance under the
      crosshair; walls occlude selection and streaming is the distance bound.
    - Invalid/unmanaged selection explains the reason; unavailable entities are
      selected only through F7.
    - Success opens F7 on the Map Entity; success, cancel and error restore the
      exact previous cursor/control state.

26. As a Study Player, I want a per-entity Activation Zone, so that proximity
    can trigger the relevant card.

    Acceptance criteria:

    - New entities copy the current global radius default, initially 3 m.
    - Radius accepts 0.5–50 m in 0.5 m steps and rejects invalid input without
      silent clamping; zero is invalid.
    - Changing the global default affects only subsequently created entities.
    - Spatial interaction occurs only in the player's current
      interior/dimension.

27. As a Study Player, I want configurable automatic opening, so that cards do
    not interrupt movement unexpectedly.

    Acceptance criteria:

    - Global delay defaults to 1 second and accepts 0–60 seconds with at most two
      decimals; zero means immediate.
    - Leaving all eligible zones cancels the countdown; the nearest eligible
      entity is continuously recalculated.
    - The vehicle speed gate is always active, defaults to 10000 km/h and has no
      separate enable checkbox; zero requires a complete stop.
    - Changing interior/dimension cancels pending opening but not an already
      open Review Mode.

28. As a Study Player, I want a configurable Next Card Indicator, so that I can
    navigate toward the next Anki-selected target.

    Acceptance criteria:

    - Modes are `Show sphere and minimap`, `Show minimap only` and
      `Show nothing`; default is `Show nothing`.
    - There is no sphere-only mode.
    - If one card has several entities, only the nearest eligible entity is
      marked.
    - A temporary next-card sphere does not create a second Activation Zone or
      alter radius; overlap with permanent display produces one emphasized
      sphere.

29. As a Study Player, I want global study across loaded maps but local spatial
    interaction, so that the queue is complete without cross-world triggers.

    Acceptance criteria:

    - Valid loaded maps enter Active Map Set by default and each has
      `Include in study`.
    - `ANKIGTA Session` spans Active Map Set regardless of interior/dimension.
    - Activation, nearest list and automatic/manual proximity actions use only
      the current interior/dimension.
    - Excluding/unloading a map removes it from the next recalculation but
      preserves links.

30. As a Study Player, I want direct Teleport, so that navigation is predictable
    and does not invent safe-landing rules.

    Acceptance criteria:

    - Teleport uses the target's current position when its Runtime Instance is
      available, otherwise its authored map position/interior/dimension.
    - It may place the player in water, empty space, collision or a vehicle.
    - If the player occupies a vehicle, that vehicle and all passengers move
      together.
    - A state race resolves from one consistent target snapshot and never mixes
      current coordinates with authored world context.

31. As a Study Player, I want to start studying explicitly, so that connecting
    to Anki does not mutate queues on its own.

    Acceptance criteria:

    - `Начать обучение` is the only transition from connected-paused to session
      startup.
    - Startup validates supported Anki/FSRS configuration, Bound Anki
      Collection, Reviewer arbitration and unresolved Review Transaction state.
    - Only successful startup creates `ANKIGTA Session`, activation and
      indicators.
    - Failure leaves study paused and does not strand cards in a filtered deck.

32. As a Study Player, I want one owned rescheduling `ANKIGTA Session`, so that
    Anki remains responsible for queue and FSRS behavior.

    Acceptance criteria:

    - The add-on builds the deck from unique eligible Anki Card Identity values
      in Active Map Set and detects name/ownership collision.
    - New, learning, relearning, due review and explicitly enabled early cards
      use Anki's scheduler; suspended/buried do not enter.
    - Pause/stop returns cards to original decks and removes the owned temporary
      deck.
    - No input ordering of `cardId` is interpreted as scheduler order.

33. As a Study Player, I want Exact Card Admission, so that a selected
    non-top card can be rated legitimately.

    Acceptance criteria:

    - The companion rebuilds the owned deck to X-only and observes Card X as
      scheduler-top before exposing rating.
    - Failure to observe X as scheduler-top makes that opening Preview only and
      performs no scheduler mutation.
    - After rating/reconciliation, the full exact-ID set is rebuilt.
    - One accepted rating produces exactly one target `revlog` entry.

34. As a Study Player, I want all linked new cards available, so that source
    deck daily limits do not hide spatial targets.

    Acceptance criteria:

    - `ANKIGTA Session` includes all linked new cards regardless of original
      new-card daily limit.
    - A card beyond today's original-deck limit remains rateable and shows
      `Новая карточка вне сегодняшнего лимита Anki`.
    - ANKIGTA implements no independent daily limit or scheduler.
    - The production Anki integration must prove its classification query on
      every supported version before the warning is enabled.

35. As a Study Player, I want early review disabled by default, so that not-due
    cards are not scheduled accidentally.

    Acceptance criteria:

    - Not-due Card defaults to Preview only and is excluded from session,
      automatic activation and indicator.
    - `Разрешить досрочное повторение` includes it through supported Anki
      early-review behavior and shows a warning.
    - The setting never overrides suspended/buried.
    - If the supported Anki build cannot perform the operation, the card
      degrades to Preview only without mutation.

36. As a Study Player, I want unavailable cards to remain inspectable, so that
    temporary Anki status does not destroy links.

    Acceptance criteria:

    - Suspended and Buried cards remain visible with status and Preview only.
    - They are absent from session, statistics, automatic activation and Next
      Card Indicator.
    - Removing the Anki status returns them automatically after state refresh.

37. As a Study Player, I want the normal question-answer-rating flow, so that
    the game uses familiar Anki semantics.

    Acceptance criteria:

    - Review Mode opens question, explicitly reveals answer, then offers
      Again/Hard/Good/Easy only for scheduler-admitted cards.
    - `Esc` closes without creating a rating when none was submitted.
    - After submission, buttons cannot submit a second logical request while
      the same Review Transaction is pending.
    - `Close after rating`, when enabled, closes after any accepted rating,
      including Again.

38. As a Study Player, I want best-effort stock MTA CEF rendering, so that more
    real Anki cards remain usable without a fragile feature whitelist.

    Acceptance criteria:

    - HTML, CSS, JavaScript and media references are delivered without
      intentional content removal, but pixel/behavioral equivalence with Anki
      Desktop is not promised.
    - Rendering, script, template or media errors show warnings and never
      disable Again/Hard/Good/Easy.
    - A missing individual media file shows a placeholder/warning and does not
      block rating.
    - Rating an incomplete or broken presentation remains an explicit user
      choice.

39. As a Study Player, I want external resources to use stock MTA behavior, so
    that remote images, fonts, styles and scripts can work.

    Acceptance criteria:

    - External HTTP(S) domains use stock MTA domain permissions.
    - The same permission may allow main-frame navigation inside the card
      surface; ANKIGTA does not promise pre-navigation blocking.
    - External Card Page keeps Again/Hard/Good/Easy enabled.
    - `Вернуться к карточке` requests a fresh render of the current side but is
      optional.
    - Popups remain stock-blocked; system-browser handoff, downloads and
      third-party page behavior are unsupported.

40. As a Study Player, I want card audio and game audio controlled separately,
    so that studying media does not force one global sound policy.

    Acceptance criteria:

    - Current-side audio is requested and played best effort like other card
      media.
    - Card media volume and game-world muting are separate client settings.
    - Closing Review Mode restores the exact prior game-audio state.

41. As a Study Player, I want each rating to be exactly one Review Transaction,
    so that retries cannot double-review a card.

    Acceptance criteria:

    - Each attempt has immutable collection UUID, cardId, rating and
      `reviewTransactionId`.
    - Identical retry returns the durable result without another scheduler call.
    - A retry that changes collection/card/rating is rejected without mutation.
    - `requestId` correlates transport and never substitutes for
      `reviewTransactionId`.

42. As a Study Player, I want automatic rating recovery, so that crashes do not
    force me to guess whether Anki changed.

    Acceptance criteria:

    - The durable journal records intent before scheduler invocation and enough
      before/after card, FSRS and `revlog` evidence to reconcile.
    - Proven applied returns `Rating applied` without a second scheduler call.
    - Proven unapplied resends the same transaction at most once and returns
      `Rating resent`.
    - Indeterminate result becomes durable Outcome Unknown, is never blindly
      resent and excludes only that card while showing `Verifying rating`.
    - Session restoration and collection change wait for reconciliation.

43. As a Study Player, I want an honest boundary around atomic Anki failures, so
    that unproved recovery is not described as exactly-once certainty.

    Acceptance criteria:

    - Process termination before call, after Anki commit and after durable
      result is covered by automated recovery tests.
    - A fault injected inside Anki's atomic answer/rebuild boundary either
      reconciles from authoritative evidence or remains Outcome Unknown.
    - Absence of a native commit receipt is documented; `revlog` timestamp alone
      is never treated as transaction identity.
    - Journal garbage collection never removes a record required for recovery.

44. As a Study Player, I want standard Anki Reviewer and ANKIGTA study to be
    mutually exclusive, so that two interfaces cannot own one scheduler queue.

    Acceptance criteria:

    - Starting normal Reviewer pauses ANKIGTA, resolves any submitted Review
      Transaction and cleans the owned filtered deck.
    - An unrated standard Reviewer question/answer may close through the
      version-gated tested AQT surface without mutation.
    - If a standard Reviewer rating callback is in flight, ANKIGTA shows
      `Завершаем оценку Anki…`, leaves Reviewer state intact and waits.
    - Timeout never forces cleanup or monkey-patches the callback; session
      startup remains blocked.
    - Completion never automatically resumes ANKIGTA study.

45. As a Study Player, I want user-initiated AnkiWeb sync to take priority, so
    that ANKIGTA does not compete with Anki synchronization.

    Acceptance criteria:

    - ANKIGTA never starts or waits for AnkiWeb sync and exposes no sync setting.
    - Sync closes an unrated Review Mode, reconciles a submitted rating, cleans
      the filtered deck and pauses study.
    - Study does not resume automatically after sync.

46. As a Study Player, I want safe pause and shutdown, so that cards return to
    their original decks.

    Acceptance criteria:

    - `Pause studying` disables activation/indicator and empties the session
      without deleting links.
    - Normal resource stop or MTA exit cleans and removes the owned filtered
      deck and closes Companion Connection.
    - ANKIGTA never closes Anki Desktop.
    - Installation, update, pause and removal acceptance tests verify no card is
      stranded in `ANKIGTA Session`.

47. As a Study Player, I want an open review to finish across world edits, so
    that transient map changes do not interrupt a submitted decision.

    Acceptance criteria:

    - Map unload, Runtime Instance destruction or Spatial Link change does not
      cancel an already open review.
    - After close/reconciliation, session, statistics and markers use current
      world/link state.
    - A collection mismatch or lost Anki connection may block a new rating, but
      the Review Mode remains closable.

48. As a Study Player, I want Review Mode to restore game state exactly, so that
    studying never leaves controls, cursor, camera or protection stuck.

    Acceptance criteria:

    - Review Mode is modal; F7, E, 1–9, plus and minus do not trigger ANKIGTA
      game actions while open.
    - Alt+Tab does not close or rate; returning asks for a click to restore focus.
    - Close, CEF failure, resource restart and disconnect restore the captured
      prior cursor, controls, camera, game sound and protection state.
    - Recovery restores prior values rather than blindly enabling everything.

49. As a Study Player, I want Review Protection independent from control
    disabling, so that I can choose interaction and damage policies separately.

    Acceptance criteria:

    - Both settings default enabled and may be changed independently.
    - While protected, the Study Player and occupied vehicle receive no new
      damage; existing health is not restored and the world is not frozen.
    - Protection ends with Review Mode and survives no crash as a stuck state.

50. As a Study Player, I want useful statistics without duplicate counting, so
    that multiple world links do not inflate study workload.

    Acceptance criteria:

    - HUD shows `Total`, `New`, `Learning`, `Due` and `Early`.
    - Counts use unique Anki Card Identity, not Spatial Link count.
    - `Total` is the union of the other four categories.
    - `Early` is always visible and equals zero when disabled/empty.
    - Suspended, buried, Card missing and Pending Map Save are excluded.

51. As a Study Player, I want F7 to manage all loaded Map Entity, so that
    unavailable runtime objects remain administrable.

    Acceptance criteria:

    - F7 lists all managed Map Entity from loaded maps with identity/link/status,
      including Entity missing and unavailable Runtime Instance.
    - Search and filtering do not depend on current streaming.
    - Destructive actions require confirmation; ordinary edits immediately
      update the server-owned model and Change History.
    - No bulk linking, CSV import or batch metadata editing is present.

52. As a Study Player, I want settings stored by the component that owns their
    behavior, so that synchronization has one authority.

    Acceptance criteria:

    - Server storage owns world/study settings and Change History.
    - MTA client owns language, UI scale, key bindings, volume/media, world
      muting, control disabling, window/HUD placement and Close after rating.
    - Companion add-on owns listener/token and Anki compatibility internals.
    - Manual connection overrides remain local to their side and do not enter
      Change History.

53. As a Russian or English user, I want localized UI, so that all product
    controls and errors are understandable.

    Acceptance criteria:

    - v1 ships Russian and English; first selection follows Windows locale
      (Russian for Russian locale, otherwise English).
    - Language changes without resource restart.
    - All product strings are UTF-8 localization entries; card text, user names,
      Entity Tag and Anki Tag are not translated.
    - Missing translation falls back to English and emits diagnostics.

54. As a Study Player, I want scalable movable UI, so that ANKIGTA remains
    usable at common resolutions.

    Acceptance criteria:

    - UI Scale defaults to 1, accepts 0.5–2 with 0.05 controls and up to two
      decimal places, and applies immediately.
    - F7 and Review Mode drag by title; HUD moves only in Edit HUD layout.
    - Placement is stored as normalized client coordinates outside Change
      History and clamped so a title remains reachable after resolution/aspect
      changes.
    - `Reset UI layout` is always reachable.
    - 1280×720, 1920×1080 and 3840×2160 pass layout acceptance tests.

55. As a Study Player, I want keyboard and mouse behavior only, so that v1 does
    not imply incomplete gamepad support.

    Acceptance criteria:

    - No gamepad navigation, prompts, remapping or future-support promise exists.
    - A connected gamepad does not trigger accidental ANKIGTA actions or
      interfere with CEF focus.

56. As a Study Player, I want automatic rotating database backups, so that
    migrations and corruption are recoverable.

    Acceptance criteria:

    - A verified backup is created before every SQLite migration.
    - After data changes, at most one daily backup is added per day.
    - Rotation retains seven daily and three pre-migration copies.
    - Backup creation is atomic, contains server SQLite only and does not block
      F7 opening.
    - Corruption never causes silent rollback: a recovery screen lists verified
      copies, preserves the damaged database and restores only the user's choice.

57. As a maintainer, I want version-pinned compatibility gates, so that a new
    Anki or MTA build cannot silently change scheduler/transport behavior.

    Acceptance criteria:

    - Initial supported matrix contains Windows, Anki Desktop 26.05 with V3
      scheduler and FSRS, and MTA Server 1.6 release build 24124.
    - Another Anki build must pass filtered-deck, rating/recovery and Reviewer
      arbitration suites before session creation and ratings are enabled.
    - Another MTA build must pass IPv4 transport and stock CEF smoke/lifecycle
      suites before it is listed as supported.
    - On an unsupported Anki build, Preview may work but session creation and
      ratings are blocked.

58. As a Study Player, I want defined performance limits, so that supported
    data volumes remain responsive.

    Acceptance criteria:

    - Reference hardware is Windows, 4-core CPU, 16 GiB RAM and SSD with MTA and
      Anki running.
    - The acceptance dataset contains 10,000 Map Entity, 5,000 Spatial Link and
      100,000 Anki cards.
    - F7 is available within 2 seconds; search/filter responds within 150 ms.
    - Pick Entity, Activation Zone and HUD add no more than 2 ms average frame
      time.
    - Card Picker first page, card open and rating confirmation complete within
      1 second for 95% of local requests.
    - Full 5,000-link session rebuild completes within 5 seconds while UI
      remains responsive and shows progress.
    - CEF never eagerly loads the entire collection.

59. As a Study Player, I want graceful behavior above the tested volume, so
    that scale degradation cannot become data loss.

    Acceptance criteria:

    - Exceeding the reference volume may show a warning and run slower.
    - It never truncates persisted links, silently skips writes or corrupts
      SQLite/Anki/map data.

60. As a maintainer, I want diagnostics without secrets, so that failures are
    actionable.

    Acceptance criteria:

    - Logs correlate requests by `requestId` and ratings by
      `reviewTransactionId`, but omit tokens and full sensitive card content.
    - Connection, protocol, collection, session, render and recovery errors have
      stable categories and localized user messages.
    - HTTP `200` is accepted only with correct Content-Type, protocol version,
      JSON envelope, required fields and matching identities.

## Implementation Decisions

1. **Component boundaries**

   - MTA server is authoritative for Map Entity records, Spatial Link,
     server-owned settings, Change History, spatial eligibility and all calls to
     companion control API.
   - MTA client is authoritative for presentation, input, CEF lifecycle, local
     sound and UI placement. It never calls companion control API directly.
   - Companion add-on is authoritative for Bound Anki Collection observation,
     collection UUID, scheduler interaction, `ANKIGTA Session`, Review
     Transaction coordination, rendering material and connection publication.
   - Anki remains authoritative for all study data and scheduling mutations.

2. **Persistent server model**

   The SQLite model contains, at minimum:

   - Map record keyed by `ankigtaMapId`, with current resource/map locator,
     `Include in study` and identity status;
   - Map Entity record keyed by `ankigtaMapId + ankigtaEntityId`, with type,
     authored transform/world context, display metadata, radius and
     `Show radius`;
   - Spatial Link with exactly one Map Entity key and one Anki Card Identity;
   - bounded Change History entries containing reversible before/after values;
   - server-owned settings and schema version.

   Foreign-key and uniqueness constraints enforce one link per Map Entity and
   reject duplicate persistent IDs. Migrations run in SQLite transactions and
   require a verified pre-migration backup.

3. **Map/link state model**

   A Map Entity/link is one of:

   - identified and unlinked;
   - Pending Map Save;
   - active Spatial Link;
   - identity collision;
   - Entity missing;
   - Card missing.

   Only active Spatial Link with an eligible Anki Card participates in session,
   statistics and spatial activation. Runtime destruction is an availability
   flag, not a persistent identity state.

4. **Collection identity registry**

   The add-on maintains an add-on-owned collision-resistant UUID in collection
   configuration plus a local registry sufficient to distinguish a present
   original from a restored/moved absent instance. UUID creation/replacement is
   atomic relative to opening the collection. Failure leaves the collection
   unbound and performs no link import.

5. **Session state model**

   The externally observable states are:

   - disconnected;
   - connected-paused;
   - waiting for standard Reviewer callback;
   - starting/rebuilding;
   - active;
   - pausing/cleaning;
   - reconciling.

   Connection/reconnection ends in connected-paused. Only explicit
   `Начать обучение` may enter starting. Any transition that encounters
   Outcome Unknown remains reconciling and cannot rebuild the deck.

6. **Exact Card Admission contract**

   The companion owns one rescheduling filtered deck. Admission is:

   - persist/validate no conflicting Review Transaction;
   - rebuild the owned deck to exact X-only membership;
   - ask Anki for scheduler-top and compare full Anki Card Identity;
   - render question/answer;
   - create and process one Review Transaction;
   - reconcile durable result;
   - rebuild full eligible membership.

   A mismatch at the scheduler-top check produces Preview only and no rating
   call.

7. **Review Transaction journal**

   The durable key is `collection UUID + reviewTransactionId`. Immutable request
   fields are cardId and rating. The journal records intent before scheduler
   invocation, before-state evidence, phase, after-state/result evidence and
   reconciliation status.

   Terminal states include applied, rejected and cancelled-before-call.
   Nonterminal states include prepared, call-started, result-durable and
   Outcome Unknown. Identical replay returns the existing result; conflicting
   replay is rejected. Journal retention must outlive all possible MTA retries
   and session recovery; garbage collection deletes only terminal entries whose
   result is no longer referenceable by either side.

8. **Control transport**

   - Listener binds only numeric `127.0.0.1`.
   - Every request carries protocol identity/version and `requestId`; review
     operations additionally carry `reviewTransactionId`.
   - Control JSON request/response size is capped at 2 MiB.
   - Read operations may execute concurrently through a bounded queue; review
     mutations are serialized by the companion coordinator.
   - Ordinary timeout is 5 seconds; read-only retry count is one; rebuild
     timeout is 30 seconds.
   - A local timeout/abort synthesizes a terminal transport outcome even if MTA
     provides no callback; a late callback is quarantined by request identity.

9. **Logical companion control operations**

   The versioned control contract provides operations for:

   - health/protocol and current collection/session status;
   - binding and validating collection identity;
   - card search/state refresh and statistics;
   - session start, full rebuild, pause and cleanup;
   - exact-card admission and question/answer render issuance;
   - Review Transaction submit, status and reconciliation.

   Operations return a common envelope containing protocol version, matching
   request identity, success/error category and operation-specific payload.
   Mutation operations are idempotent or explicitly conflict-detecting.

10. **Connection configuration publication**

    Companion add-on is the sole automatic writer. It writes a complete
    versioned candidate, validates it, atomically replaces current configuration
    and retains exactly one last-known-good version. MTA validates
    format/version/protocol identity before use and falls back with an explicit
    error. If neither version validates, it stays disconnected.

11. **Read-only card content contract**

    The content listener is separated from control dispatch and supports only
    GET/HEAD for issued render resources. A capability has at least 256 bits of
    randomness and binds collection, card, side and render generation.

    Initial v1 guardrails are the values already exercised by Prototype 0006:

    - 15-second issuance lifetime plus close/generation revocation;
    - maximum 64 requests and 32 MiB unique bytes per render;
    - HTML up to 4 MiB and one media response up to 16 MiB;
    - at most four concurrently serviced content requests;
    - normalized identical Range retry does not consume unique-byte budget twice;
    - Range returns 206; overload returns bounded 503;
    - responses use no-store, no-referrer and nosniff headers.

    These are initial implementation limits, not rendering guarantees. A limit
    failure produces a visible warning while rating remains available.

12. **Stock MTA CEF contract**

    The child surface is a remote stock-MTA browser. A card-visible
    `window.mta` stub is accepted because native remote dispatch denial is the
    actual privileged boundary. External domain permissions may also permit
    child-surface main-frame navigation. The outer Review Mode remains owned by
    Lua/dx and keeps rating controls available. No native fork, JavaScript
    rewriting security boundary, system-browser guarantee or download support
    is required.

13. **Review Mode state**

    Review Mode tracks closed, question, answer, submitting and External Card
    Page presentation. Rendering warnings are orthogonal flags and never disable
    rating. Scheduler/collection/connection availability may disable a new
    rating because Anki cannot accept it; the window itself remains closable.

14. **World/runtime indexing**

    Server maintains persistent Map Entity records while client maintains a
    current mapping to streamed Runtime Instance. Spatial checks use current
    position and current interior/dimension; queue membership does not.
    Teleport resolves one consistent snapshot before acting.

15. **Input and restoration**

    Every modal client mode captures the prior cursor, control, camera, audio
    and protection state and restores that snapshot on every exit path. Review
    Mode and Pick Entity have separate state machines; neither uses unconditional
    global enable calls for cleanup.

16. **Backups and Change History**

    Change History is a product undo log, not a database backup or Anki
    transaction log. SQLite backup rotation is independent and cannot be undone.
    Connection configuration and UI placement are stored outside both.

17. **Version support**

    v1 initially enables scheduling only for the exact tested Anki/FSRS matrix
    and transport only for the tested MTA build. Compatibility expansion is a
    data-driven release operation after the same integration suites pass; it is
    not inferred from semantic version numbers.

18. **Known technical release gates**

    The following are required implementation proofs, not already-proven facts:

    - atomic collection UUID assignment and copied-collection detection;
    - production durable journal storage/garbage collection and an injected
      fault inside Anki's atomic answer/rebuild boundary;
    - versioned full/X-only session API and supported daily-limit warning query;
    - version-gated Reviewer close/callback completion without forced cleanup;
    - atomic connection configuration publication with last-known-good fallback;
    - real Map Editor Save/read-back/copy/collision end-to-end scenarios;
    - real MTA CEF best-effort render, media, focus and lifecycle smoke tests;
    - scheduler-derived statistics without reimplementing scheduling;
    - ACL enforcement, Review Protection damage coverage, Pick Entity occlusion
      and world-context race tests;
    - performance and migration/backup recovery suites.

    A ticket may implement the relevant seam, but the dependent production path
    remains disabled until its gate passes.

19. **MTA/GTA implementation boundary**

    Implementation and code-review agents must obey the repository
    MTA/GTA reference-only policy. Installed MTA/GTA directories, processes,
    configuration, logs, resources, registry state and user maps are outside
    their writable and executable scope.

    The provided MTA source tree is a concurrently used read-only reference:
    only relevant files may be searched/read, with no edits, builds, tests,
    generated caches or Git/worktree operations. Material source conclusions
    retain per-file provenance and hashes.

    Every ticket whose final acceptance mentions real MTA, Map Editor, CEF or
    GTA must split verification into repository-local automated coverage and a
    manual runtime checklist. Ordinary implementation leaves the latter
    explicitly `not run`; only a separate user-authorized runtime validation
    may execute it.

## Testing Decisions

1. **Primary seam**

   The final highest-value validation drives a real Study Player through public
   UI/actions while using a supported Anki Desktop, MTA Server and MTA Client.
   Implementation agents prepare its harness/checklist but do not execute
   installed MTA/GTA. Its canonical tracer scenario is:

   `Map Entity → Spatial Link → verified Map Editor Save → Activation Zone →
   question → answer → rating → reconciled Anki result → updated next target`.

   Assertions observe UI state, persisted identity/link state, Anki card/FSRS
   state, `revlog`, filtered-deck cleanup and restored MTA controls. They do not
   assert private function calls.

2. **Companion contract seam**

   A process-level contract suite calls the versioned loopback API through the
   same HTTP surface as server-side Lua. It covers schema validation, identity
   matching, 2 MiB limits, timeouts, one read retry, serialized ratings,
   duplicate/conflicting Review Transaction requests, malformed HTTP 200,
   disconnect and late callback quarantine.

3. **Durable recovery seam**

   Deterministic fault injection terminates the companion:

   - before scheduler call;
   - after Anki commit but before durable result;
   - after durable result but before response;
   - during full/X-only rebuild;
   - during cleanup and restart.

   Each test asserts zero or one scheduling mutation, never two. If authoritative
   evidence cannot decide, it asserts durable Outcome Unknown and isolation of
   only the affected card.

4. **Anki compatibility suite**

   For every supported Anki build, run new, learning, relearning, due review and
   future review through all four ratings and compare semantic card, FSRS and
   `revlog` results to control Anki behavior. Separately verify
   suspended/buried Preview only, daily-limit warning, profile/collection
   detection, standard Reviewer arbitration and AnkiWeb sync.

5. **Map Editor identity suite**

   Repository-local source-contract/fixture tests cover identity parsing,
   collision handling and read-back orchestration. A separately authorized
   manual stock Map Editor checklist covers object, vehicle and ped assignment,
   Save/read-back, close/reopen, move/model edit, rename, clone, resource copy,
   Save As, unsaved close, interrupted save, duplicate collision and
   `Проверить ещё раз`. Until executed, its runtime result remains `not run`.

6. **CEF/content suite**

   Repository-local contract/corpus tests cover capability
   entropy/binding/expiry/revocation, GET/HEAD, Range, retry budget, limits,
   missing media, uniform denial and four-request backpressure. A separately
   authorized manual MTA CEF checklist covers representative
   HTML/CSS/JavaScript, local/external media, audio, render errors, external
   navigation, optional return, focus, Esc, resource restart and cleanup.
   Pixel-perfect comparison is not a pass criterion; rating controls remain
   enabled on errors and External Card Page.

7. **MTA gameplay suite**

   Tests cover ACL rejection, dynamic object/vehicle/ped movement/destruction,
   spatial indexing, current interior/dimension filtering, delay/speed races,
   Pick Entity occlusion and cleanup, direct Teleport with vehicle/passengers,
   Review Protection damage sources and exact restoration of prior client state.

8. **Persistence suite**

   Schema migration tests start from every shipped schema version, create the
   required pre-migration backup, verify constraints/data, and inject write
   failure. Change History tests cover the 100-entry bound, restart persistence,
   Undo/Redo branch truncation and excluded operations. Corruption recovery
   tests verify explicit user choice and preservation of the damaged database.

9. **Performance suite**

   Use the reference hardware/data envelope from User Story 58. Measure p95
   local interaction latency, F7 startup/search, frame-time contribution and
   session rebuild while UI stays responsive. Results above the thresholds block
   release for that supported matrix.

10. **Prior art**

    Prototype 0001 supplies the non-top rejection control; Prototype 0002
    supplies filtered-deck/FSRS admission scenarios; Prototype 0003 supplies
    durable recovery and lifecycle fault boundaries; Prototype 0004 supplies
    real MTA IPv4 transport scenarios; Prototype 0005 supplies stock Editor
    serialization/collision constraints; Prototype 0006 supplies content
    capability and stock CEF constraints. Prototype harness code is disposable;
    scenario intent and observable evidence are retained.

11. **Release rule**

    No test may convert an unknown outcome into success by retrying a different
    logical rating, writing scheduling SQL, editing `.map` in the background,
    forcing Reviewer cleanup, binding externally or claiming unsupported CEF
    isolation. An unexecuted real-runtime checklist remains `not run` and is not
    equivalent to failure or success. A failed release gate disables only its
    dependent feature where the spec defines a fallback; otherwise it blocks
    the supported build.

## Out of Scope

- Multiplayer study, one collection per player, shared cards or non-admin Study
  Player access.
- Any gamepad UI, navigation, remapping or future gamepad roadmap.
- Linux/macOS support, mobile Anki, AnkiWeb API integration or remote/LAN
  companion connections.
- Automatic Anki launch, profile switching, add-on installation/update or Anki
  process shutdown.
- A custom scheduler, private Anki queue mutation, direct scheduling SQL writes
  or heuristic card replacement.
- A native/upstream MTA fork, custom Map Editor fork or background `.map` edits.
- Whole-save atomicity or external-change protection for stock Map Editor.
- Pixel-perfect Anki/CEF equivalence, exhaustive HTML/CSS/JavaScript whitelist,
  guaranteed system-browser links, downloads or control of third-party pages.
- Protection against a malicious local administrator/process; encrypted secret
  vault.
- Batch link creation, CSV/table import, batch metadata editing or other bulk
  ANKIGTA operations.
- Independent per-map/per-deck settings except `Include in study` and defined
  Map Entity fields.
- AnkiWeb sync controls, cloud backup/sync and ordinary manual backup management
  inside F7.
- Safe-landing Teleport search, ANKIGTA-owned respawn or world freezing.
- Exact visual color polish as a release blocker.

## Further Notes

- Source precedence for this spec is the current glossary, accepted ADRs,
  confirmed baseline and Prototype 0001–0006 results. The old preliminary
  `ANKIGTA_SPEC.md` is intentionally not a source and is not modified.
- ADR 0026 supersedes the strict bridge/navigation/system-browser portions of
  ADR 0010. ADR 0027 supersedes semantic-equivalence and render-error rating
  blocks. The operative v1 contract is stock-MTA best effort with ratings left
  available on errors and External Card Page.
- Prototype verdicts remain scoped: 0002 passed; 0001, 0005 and 0006 failed;
  0003 and 0004 partially passed. Accepted fallbacks close the product decisions
  but do not manufacture missing runtime proof.
- Implementation tickets must preserve blocking edges from the technical
  release gates. In particular, UI work must not make a path appear enabled
  before its collection/session/recovery compatibility gate passes.
- v1 is complete only when the canonical end-to-end scenario, recovery,
  migration, Map Editor, CEF lifecycle and performance suites pass on the
  documented supported matrix and installation/removal leaves no stranded
  filtered-deck cards or lost Spatial Link.

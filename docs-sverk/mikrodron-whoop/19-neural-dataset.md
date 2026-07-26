# Сбор датасета в Roboflow

> Раздел: Микродрон (Whoop) · slug: `neural-dataset`
> Источник: https://edu.sverk.tech/learn/whoop/neural-dataset

---

# Сбор датасета в Roboflow


Для сбора датасета воспользуйтесь платформой [Roboflow](https://app.roboflow.com/).

- После авторизации перейдите на вкладку «**Train and improve datasets and models**».

![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=whoop%2Fassets%2Fneural-dataset%2Fimage1.png&sig=bda45aacb8a35a260d34c006ced50c55effeca8895c3c4666933ac4f56088c22)


- Создайте новый проект, нажав «**New project**», введите название проекта.

![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=whoop%2Fassets%2Fneural-dataset%2Fimage2.png&sig=90918a1c81a46f915fccfd3f2684854cf4052e2cead603049c855097a14a751c)


- Введите название проекта (латиницей), например «Sverk». Выберите тип проекта и нажмите продолжить.

![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=whoop%2Fassets%2Fneural-dataset%2Fimage3.png&sig=8795f44c31335557d15036407beb8de4c55368ff8cf415e3f6492bccc8dc403b)



Рассмотрим пример модели, распознающей объекты.

- Загрузите видео с объектами, которые нужно распознать, с помощью кнопки «**Select File(s)**».

![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=whoop%2Fassets%2Fneural-dataset%2Fimage4.png&sig=d997f7a1971fe713a1c38585fba17a848e5880a23922246aabce221224105459)


- Выберите частоту создания кадров так, чтобы их количество получилось около 11—15, нажмите «**Extract … frames**».

![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=whoop%2Fassets%2Fneural-dataset%2Fimage5.png&sig=c4f77b4c42ae375f35a900e11b1575fbefed9f93846b3ef31ac875926d11b02b)


- Сохраните, нажав «**Save and Continue**».

![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=whoop%2Fassets%2Fneural-dataset%2Fimage6.png&sig=799eb52a224bf2d923daa44709884798fc7927f44de49924ff94c0f1e8d87c36)


- Перейдите на вкладку «**Annotate**». Для разметки объектов вручную нажмите «**Label Myself**».

![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=whoop%2Fassets%2Fneural-dataset%2Fimage7.png&sig=a95577a76795b0c4fa9fbdc94ce9a2d6a2127e724edf10d3b63f410be2c2a202)


- Выделите нужный объект одним из трёх инструментов: «**прямоугольное выделение**», «**полигон точек**», «**умное выделение**».

![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=whoop%2Fassets%2Fneural-dataset%2Fimage8.png&sig=e6f1142e60ff4fa0efa81bc0224e3108c6b1dee6e3babbb24aca2e7e65564516)


- После выделения нажмите **Enter** или «**Finish (Enter)**».

![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=whoop%2Fassets%2Fneural-dataset%2Fimage9.png&sig=287566348cda4ceaae87329696e75e77fba3fc8f0fca1de6dd9032b03f23903c)


- Введите название объекта (латиницей), например «**haystack**» — стог сена.

Здесь же можно уточнить границы объекта, изменив положение точек или добавив новые.


![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=whoop%2Fassets%2Fneural-dataset%2Fimage10.png&sig=eda00c9a2bc2ce3552e59b51fd6fb3d33378d8c912f4fd1a54ff0a28b8f970b4)


- Разметьте все объекты одного класса на изображении, присвоив им одинаковое название. Нажмите галочку для сохранения.

![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=whoop%2Fassets%2Fneural-dataset%2Fimage11.png&sig=9edade272afe16d7b78fe2dd15cfa99fb04c52f85d4398e0d9465f210bcffb3f)


-

Повторите для всех изображений (около 15).

-

Перейдите на вкладку «**Dataset**» и сохраните датасет, нажав «**Export**».


![](https://api.edu.sverk.tech/api/courses/import/gitlab/asset?origin=https%3A%2F%2Fgit.sverk.io&project=SES%2Fdocs&ref=main&path=whoop%2Fassets%2Fneural-dataset%2Fimage12.png&sig=9a683a01fc47a107373f385973667ebb24fe99475d070f8aa2b5cc973398c940)


- В качестве формата экспорта выберите **YOLOv11**. Roboflow выдаст код для скачивания датасета — он используется в статье «[Обучение модели YOLO11](/learn/whoop/neural-training)».

>

**Примечание** Формат экспорта должен соответствовать версии модели. Для YOLO11 выбирайте **YOLOv11**.

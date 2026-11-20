import 'package:flutter/material.dart';

import 'viability/viability_page.dart';

void main() {
  runApp(
    MaterialApp(
      theme: ThemeData(fontFamily: 'Roboto'),
      debugShowCheckedModeBanner: false,
      home: ViabilityPage(),
    ),
  );
}
